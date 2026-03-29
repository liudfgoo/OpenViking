# 代码架构：OpenViking

## 整体架构概述

OpenViking 采用**分层模块化架构**，核心设计理念是"基础设施即服务"。架构分为四个主要层次：

1. **存储层**：AGFS（Agent File System）提供虚拟文件系统抽象
2. **索引层**：自研 C++ 向量索引引擎，支持稠密/稀疏/混合检索
3. **服务层**：Python 实现的业务逻辑和 HTTP API
4. **客户端层**：多语言客户端（Python SDK、Rust CLI、HTTP API）

架构风格：**管道式 + 插件化**，通过 QueueManager 实现异步任务处理，支持水平扩展。

## 模块划分

| 模块名 | 职责 | 对外接口 |
|--------|------|----------|
| **AGFS** | 虚拟文件系统，提供 `viking://` 协议的存储抽象 | `AGFSClient` / `AGFSBindingClient` |
| **VikingFS** | 在 AGFS 之上提供语义层，管理 L0/L1/L2、关系、检索 | `VikingFS` 类（单例） |
| **VikingDBManager** | 向量存储管理，封装向量索引和队列 | `VikingDBManager` 类 |
| **HierarchicalRetriever** | 分层检索引擎，实现目录递归检索算法 | `retrieve()` 方法 |
| **OpenVikingService** | 主服务类，组合所有子服务 | FastAPI HTTP 接口 |
| **SessionManager** | 会话管理，自动压缩和记忆提取 | `Session` 类 |
| **ResourceProcessor** | 资源处理器，支持多格式文档解析 | 异步处理管道 |
| **QueueManager** | 任务队列管理，支持嵌入和语义处理异步化 | `QueueManager` 类 |
| **VikingBot** | AI Agent 框架（可选组件） | `vikingbot` CLI |

## 关键数据流

### 1. 资源写入流程

```
用户输入 (URL/文件/文本)
        ↓
ResourceProcessor.parse()
        ↓
[格式检测] → PDF/DOCX/MD/HTML/...
        ↓
内容提取 + 图片提取
        ↓
VLM 生成描述 (图片理解)
        ↓
AGFS.write() → 存储原始内容 (L2)
        ↓
EmbeddingQueue.enqueue() → 异步处理
        ↓
生成 L0 (abstract) + L1 (overview) + 向量
        ↓
VikingDBManager.upsert() → 向量索引
```

### 2. 检索流程 (find/search)

```
用户查询
    ↓
[search() 才有此步骤] IntentAnalyzer.analyze()
    ↓
生成 TypedQuery（1-5 个）
    ↓
Embedder.embed() → 查询向量
    ↓
HierarchicalRetriever.retrieve()
    ↓
Step 1: 确定根目录（根据 context_type）
    ↓
Step 2: 全局向量搜索定位起始点
    ↓
Step 3: Rerank 精排（THINKING 模式）
    ↓
Step 4: 递归搜索（优先级队列）
    ↓
Step 5: 分数传播 + 收敛检测
    ↓
返回 MatchedContext 列表
```

### 3. 会话管理流程

```
Session.add_message()
    ↓
触发自动压缩检查
    ↓
超过阈值 → SessionCompressor.compress()
    ↓
提取关键信息 + 生成摘要
    ↓
MemoryExtractor.extract()
    ↓
分析用户偏好 + Agent 经验
    ↓
更新到 viking://user/memories 或 viking://agent/memories
    ↓
异步嵌入向量索引
```

## 核心抽象与设计模式

### 核心类图

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenVikingService                        │
│                    (服务组合器/外观模式)                      │
├─────────────────────────────────────────────────────────────┤
│  - _agfs_client: AGFSClient                                 │
│  - _viking_fs: VikingFS                                     │
│  - _vikingdb_manager: VikingDBManager                       │
│  - _queue_manager: QueueManager                             │
│  - _embedder: EmbedderBase                                  │
│  - fs: FSService                                            │
│  - search: SearchService                                    │
│  - sessions: SessionService                                 │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│  VikingFS    │    │ VikingDBManager │    │ AGFSManager  │
│  (单例模式)   │    │ (向量存储管理)   │    │ (AGFS 进程)  │
├──────────────┤    ├─────────────────┤    ├──────────────┤
│  - agfs      │    │ - index_engine  │    │ - agfs-server│
│  - vector_store│   │ - embedding_queue│   │              │
│  - embedder  │    │ - queue_manager │    │              │
└──────────────┘    └─────────────────┘    └──────────────┘
        │                     │
        ↓                     ↓
┌──────────────┐    ┌─────────────────┐
│HierarchicalRetriever│   │ IndexEngine (C++)│
│ (检索策略)    │    │ (自研向量索引)   │
├──────────────┤    ├─────────────────┤
│ - vector_store│   │ - dense_index   │
│ - embedder   │    │ - sparse_index  │
│ - rerank_client│  │ - scalar_filter │
└──────────────┘    └─────────────────┘
```

### 设计模式

| 模式 | 应用位置 | 说明 |
|------|---------|------|
| **单例模式** | `VikingFS`、`QueueManager`、`LockManager` | 全局唯一实例，通过 `get_*()` 访问 |
| **外观模式** | `OpenVikingService` | 封装复杂子系统，提供统一接口 |
| **策略模式** | `EmbedderBase` | 支持 Dense/Sparse/Hybrid 多种嵌入策略 |
| **工厂模式** | `AGFSClient` 创建 | 根据配置创建 HTTP 或 Binding 客户端 |
| **观察者模式** | `WatchScheduler` | 监控资源变化，触发更新 |
| **管道模式** | `ResourceProcessor` | 多阶段处理管道，支持插件扩展 |
| **代理模式** | `VikingDBManagerProxy` | 注入请求上下文，实现权限控制 |

## 扩展点

### 1. 嵌入模型扩展

```python
# 继承 EmbedderBase
class MyEmbedder(DenseEmbedderBase):
    def embed(self, text: str, is_query: bool = False) -> EmbedResult:
        # 自定义嵌入逻辑
        return EmbedResult(dense_vector=...)
    
    def get_dimension(self) -> int:
        return 768

# 配置中使用
config.embedding.provider = "custom"
config.embedding.custom_embedder = MyEmbedder()
```

### 2. 资源处理器扩展

```python
# 添加新的文件格式支持
@ResourceProcessor.register(".custom")
async def parse_custom(file_path: str) -> ParsedContent:
    # 自定义解析逻辑
    return ParsedContent(text=..., images=...)
```

### 3. Bot 技能扩展

```python
# 在 bot/workspace/skills/ 下创建 SKILL.md
# 定义技能描述、参数、执行脚本
```

### 4. 检索后处理扩展

```python
# 自定义 Rerank 客户端
class MyRerankClient:
    def rerank_batch(self, query: str, documents: List[str]) -> List[float]:
        # 自定义重排序逻辑
        return scores
```

## 依赖关系图（模块级）

```
                    ┌─────────────┐
                    │   CLI/API   │
                    │  (入口层)    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Server    │
                    │  (FastAPI)  │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
┌──────────────┐  ┌─────────────────┐  ┌──────────────┐
│   Service    │  │    Session      │  │   Storage    │
│   (业务逻辑)  │  │   (会话管理)     │  │   (存储层)    │
└──────┬───────┘  └────────┬────────┘  └──────┬───────┘
       │                   │                  │
       ↓                   ↓                  ↓
┌──────────────┐  ┌─────────────────┐  ┌──────────────┐
│   Core       │  │   Retrieve      │  │    AGFS      │
│ (核心抽象)    │  │   (检索引擎)     │  │  (文件系统)   │
└──────────────┘  └────────┬────────┘  └──────┬───────┘
                           │                  │
                           ↓                  ↓
                  ┌─────────────────┐  ┌──────────────┐
                  │   Models        │  │  src/ (C++)  │
                  │ (Embedder/VLM)  │  │ (向量索引引擎) │
                  └─────────────────┘  └──────────────┘
```

### 关键依赖原则

1. **单向依赖**：上层模块可调用下层，下层不可调用上层
2. **依赖注入**：`OpenVikingService` 初始化时注入所有依赖
3. **接口隔离**：通过抽象基类（`EmbedderBase`）定义接口
4. **无循环依赖**：模块间依赖关系为 DAG（有向无环图）
