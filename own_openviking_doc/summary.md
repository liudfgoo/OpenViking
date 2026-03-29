# OpenViking 设计与核心功能总结

## 一、项目概述

**OpenViking** 是由字节跳动（ByteDance）火山引擎（Volcengine）开发的开源**上下文数据库（Context Database）**，专为 AI Agent 设计。其核心 Slogan 是 **"Data in, Context out"**。

### 解决的问题

在 AI Agent 开发中面临的核心挑战：

| 痛点 | 传统方案的问题 | OpenViking 的解决方案 |
|------|---------------|---------------------|
| 上下文碎片化 | Memories 在代码、Resources 在向量库、Skills 散落 | 文件系统范式统一组织 |
| 上下文需求激增 | 简单截断导致信息丢失 | L0/L1/L2 三级分层按需加载 |
| 检索效果差 | 扁平存储缺乏全局视图 | 目录递归检索 + 语义搜索 |
| 不可观测性 | 检索链是黑盒难以调试 | 可视化检索轨迹 |
| 记忆迭代受限 | 只是交互记录，缺乏任务记忆 | 自动会话管理，提取长期记忆 |

### 性能数据（基于 LoCoMo 长程对话测试集）

| 实验组 | 任务完成率 | 输入 Token 成本 |
|--------|-----------|----------------|
| OpenClaw（原生） | 35.65% | 24,611,530 |
| OpenClaw + LanceDB | 44.55% | 51,574,530 |
| **OpenClaw + OpenViking** | **52.08%** | **4,264,396** |

**结论**：任务完成率提升 **49%**，Token 成本降低 **83-91%**。

---

## 二、核心设计理念

### 1. 文件系统范式（Filesystem Paradigm）

OpenViking 不将上下文视为扁平文本片段，而是统一映射为**虚拟文件系统**，通过 `viking://` URI 协议访问：

```
viking://
├── resources/              # 外部资源（文档、代码库、网页等）
│   └── user_projects/
├── user/                   # 用户记忆（偏好、习惯、身份）
│   └── memories/
│       ├── profile/        # 用户身份
│       ├── preferences/    # 用户偏好
│       ├── entities/       # 相关实体（人物、项目）
│       ├── events/         # 重要事件/决策
│       ├── cases/          # 问题案例
│       └── patterns/       # 经验模式
└── agent/                  # Agent 记忆（技能、指令、任务）
    ├── skills/             # Agent 技能
    ├── memories/          # Agent 任务记忆
    └── instructions/      # 系统指令
```

每个上下文条目都有唯一的 `viking://` URI，可通过 `ls`、`find`、`grep`、`tree` 等标准命令操作。

### 2. 分层上下文加载（L0/L1/L2）

在写入时自动将内容处理为三个层级：

- **L0（Abstract）**：一句话摘要，~100 tokens，快速相关性判断
- **L1（Overview）**：核心信息和结构，~2k tokens，规划决策
- **L2（Detail）**：完整原始内容，按需加载，深度阅读

这种分层设计显著降低了 Token 消耗（期望成本远低于直接加载 L2）。

### 3. 目录递归检索策略

**先锁定高相关目录，再精确定位内容**：

1. **意图分析**：生成多个检索条件（TypedQuery）
2. **初始定位**：向量检索快速定位高相关目录
3. **精化探索**：在目录内二次检索，更新候选集
4. **递归深入**：存在子目录时递归重复
5. **结果聚合**：返回最相关的上下文

**分数传播机制**：
$$\text{final\_score}(c) = \alpha \cdot \text{embed\_score}(c) + (1-\alpha) \cdot \text{parent\_score}$$

其中 α = 0.5，确保深层内容继承父目录相关性。

---

## 三、核心功能模块

### 1. 资源管理（Resource Management）

- **添加资源**：`add_resource()` 支持 URL、文件、目录
- **格式支持**：PDF、DOCX、Markdown、HTML、EPUB、Excel、PowerPoint、图片、音频、视频
- **语义处理**：自动生成 L0/L1 + 向量化
- **进度监控**：`wait_processed()` 等待处理完成

### 2. 文件系统操作

- **浏览**：`ls()`、`tree()` 列出目录结构
- **读取**：`read()` 读取 L2 完整内容
- **摘要**：`abstract()` 读取 L0，`overview()` 读取 L1
- **搜索**：`grep()` 文本搜索，`glob()` 模式匹配
- **操作**：`mkdir()`、`rm()`、`mv()` 目录/文件操作

### 3. 语义检索（Retrieval）

两种检索模式：

- **`find()`**：快速向量检索，无需 LLM 分析意图，延迟更低
- **`search()`**：带意图分析，会话感知的复杂检索，调用 LLM 生成 TypedQuery

关键参数：
- `target_uri`：限定检索范围
- `limit`：返回结果数量
- `score_threshold`：分数阈值过滤
- `mode`：THINKING（重排序）vs QUICK（纯向量）

### 4. 会话与记忆管理（Session & Memory）

**会话生命周期**：

```
用户消息 → add_message() → 消息记录
                          ↓
                    commit() 触发
                          ↓
         ┌────────────────┼────────────────┐
         ↓                ↓                ↓
   会话压缩        记忆提取           归档存储
  (Compressor)   (MemoryExtractor)  (Archiver)
         ↓                ↓                ↓
    精简消息       写入 viking://user/   更新摘要
                  或 viking://agent/
```

**记忆分类**：

| 类别 | URI 路径 | 示例 |
|------|---------|------|
| profile | viking://user/.../profile/ | 姓名、职位、base |
| preferences | viking://user/.../preferences/ | 工具偏好、回复语言 |
| entities | viking://user/.../entities/ | 同事、项目名 |
| events | viking://user/.../events/ | 技术决策、重要事件 |
| cases | viking://user/.../cases/ | 问题案例、解决方案 |
| patterns | viking://user/.../patterns/ | 可复用经验 |

**记忆去重（Deduplication）**：
- 同一会话多次提交 → **Merge**（合并）
- 跨会话相似记忆 → **Skip**（跳过）或 **Update**
- 冲突的记忆 → **Delete**（删除旧记忆）

### 5. 关系链接（Relations）

将相关文档链接在一起，增强检索效果：
```bash
ov link <uri1> <uri2> --reason "描述关联原因"
```

### 6. VikingBot（可选组件）

基于 OpenViking 的 AI Agent 框架，支持多平台（Telegram、Slack、Discord、飞书等），内置技能系统和沙箱执行环境。

---

## 四、架构设计

### 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI / SDK                               │
│                   (AsyncHTTPClient / SyncHTTPClient)         │
├─────────────────────────────────────────────────────────────┤
│                      OpenVikingService                       │
│                      (业务逻辑组合器)                         │
├──────────────────┬──────────────────┬────────────────────────┤
│  SearchService   │  SessionService  │  ResourceService       │
│   (检索服务)      │   (会话服务)      │   (资源服务)            │
├──────────────────┴──────────────────┴────────────────────────┤
│                     VikingFS                                │
│                (文件系统抽象层 / 单例模式)                      │
├───────────────────────────┬─────────────────────────────────┤
│   VikingDBManager         │        AGFSManager              │
│   (向量存储管理)           │        (AGFS 进程)               │
├───────────────────────────┼─────────────────────────────────┤
│ HierarchicalRetriever     │      AGFSClient                 │
│ (分层检索引擎)             │      (HTTP/Binding)             │
├───────────────────────────┼─────────────────────────────────┤
│ IndexEngine (C++)         │                                 │
│ (自研向量索引引擎)          │                                 │
│ - 稠密向量 / 稀疏向量        │                                 │
│ - 混合检索 / RRF 融合       │                                 │
└───────────────────────────┴─────────────────────────────────┘
```

### 核心技术栈

| 组件 | 技术 |
|------|------|
| 主要语言 | Python 3.10+ |
| CLI 工具 | Rust (`ov` 命令) |
| 核心扩展 | C++ (pybind11) |
| Web 服务 | FastAPI |
| 向量检索 | 自研 C++ 索引引擎 |
| 嵌入模型 | OpenAI / Volcengine / Jina 等 |
| VLM 模型 | OpenAI / Volcengine / LiteLLM 等 |
| 文件系统 | AGFS（Agent File System） |

### 设计模式

| 模式 | 应用位置 |
|------|---------|
| 单例模式 | VikingFS、QueueManager、LockManager |
| 外观模式 | OpenVikingService 封装复杂子系统 |
| 策略模式 | EmbedderBase 支持多种嵌入策略 |
| 工厂模式 | AGFSClient 根据配置创建客户端 |
| 观察者模式 | WatchScheduler 监控资源变化 |
| 管道模式 | ResourceProcessor 多阶段处理管道 |

---

## 五、代码组织

```
openviking/                    # 核心 Python 实现
├── core/                      # 核心抽象（Context、目录、Skill 加载）
│   ├── context.py             # Context 类定义（URI、level、vector 等）
│   ├── directories.py         # 目录结构初始化
│   └── skill_loader.py        # Skill 加载器
├── storage/                   # 存储层
│   ├── viking_fs.py          # VikingFS 文件系统抽象（单例）
│   ├── vikingdb_manager.py   # 向量存储管理
│   ├── vectordb/             # 向量数据库适配
│   └── queuefs/              # 队列文件系统
├── retrieve/                  # 检索引擎
│   ├── hierarchical_retriever.py  # 核心分层检索实现
│   ├── intent_analyzer.py     # 意图分析（TypedQuery）
│   └── memory_lifecycle.py   # 记忆热度评分
├── session/                   # 会话管理
│   ├── session.py            # 会话核心类
│   ├── compressor.py          # 会话压缩
│   ├── memory_extractor.py   # 记忆提取
│   └── memory_deduplicator.py # 记忆去重
├── service/                   # 业务服务层
│   ├── core.py               # OpenVikingService 主类
│   ├── search_service.py     # 搜索服务
│   └── resource_service.py   # 资源服务
├── server/                   # FastAPI HTTP 服务
├── models/                   # 模型抽象（Embedder、VLM）
├── parse/                    # 文档解析器
└── pyagfs/                   # AGFS Python SDK 封装

crates/ov_cli/                # Rust CLI 实现
src/                          # C++ 核心引擎（向量索引）
bot/                          # VikingBot Agent 框架
tests/                        # 单元测试和集成测试
examples/                     # 使用示例
```

---

## 六、公开 API

### Python SDK（本地模式）

```python
from openviking import OpenViking

client = OpenViking(path="./data")
client.initialize()

# 资源管理
res = client.add_resource(path="https://github.com/...")
root_uri = res["root_uri"]
client.wait_processed()

# 文件系统
client.ls(root_uri)
client.read(uri)
client.abstract(uri)   # L0
client.overview(uri)  # L1

# 检索
results = client.find(query="...", target_uri=root_uri, limit=5)
client.search(query="...", session=session, limit=5)

# 会话
session = client.session()
session.add_message(role="user", content="...")
session.commit()
```

### Python SDK（HTTP 模式）

```python
from openviking import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933", api_key="...")
await client.initialize()

results = await client.find(query="...", limit=5)
```

### CLI 命令

```bash
openviking-server              # 启动服务
ov status                      # 查看状态
ov add-resource <path> --uri <uri> --wait  # 导入资源
ov ls viking://resources/       # 列出目录
ov tree viking:// -L 2          # 目录树
ov find "query" --uri <scope>   # 语义检索
ov grep "pattern" --uri <scope> # 文本搜索
ov cat <uri>                    # 读取内容
ov link <uri1> <uri2>          # 创建关系链接
ov chat                         # 启动对话（Bot 模式）
```

---

## 七、关键数据流

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
VLM 生成描述（图片理解）
        ↓
AGFS.write() → 存储原始内容 (L2)
        ↓
EmbeddingQueue.enqueue() → 异步处理
        ↓
生成 L0 (.abstract.md) + L1 (.overview.md) + 向量
        ↓
VikingDBManager.upsert() → 向量索引
```

### 2. 检索流程

```
用户查询
    ↓
[search() 才有] IntentAnalyzer.analyze() → TypedQuery (1-5 个)
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
Step 5: 分数传播 + 收敛检测（最多 3 轮）
    ↓
返回 MatchedContext 列表
```

### 3. 会话管理流程

```
Session.add_message()
    ↓
触发自动压缩检查（超过阈值）
    ↓
SessionCompressor.compress()
    ↓
MemoryExtractor.extract()
    ↓
分析用户偏好 + Agent 经验
    ↓
MemoryDeduplicator.deduplicate() → merge/skip/update/delete
    ↓
更新到 viking://user/memories 或 viking://agent/memories
    ↓
异步嵌入向量索引
```

---

## 八、与传统 RAG 的对比

| 维度 | 传统 RAG | OpenViking |
|------|---------|-----------|
| 存储模型 | 扁平切片 | 文件系统层次结构 |
| 上下文层级 | 无 | L0/L1/L2 分层 |
| 检索策略 | 单一向量检索 | 目录递归检索 |
| 检索可观测性 | 黑盒 | 可视化检索轨迹 |
| 记忆管理 | 无 | 自动会话管理 + 记忆提取 |
| Token 效率 | 低（全部加载） | 高（按需加载 L0→L1→L2）|
| 关系建模 | 无 | 显式关系链接 |

---

## 九、适用场景

### 适合使用

- Agent 需要长期记忆和任务记忆
- 处理复杂、层次化的文档结构（项目文档、代码库）
- 对检索可解释性有要求（调试、优化检索逻辑）
- 希望降低 LLM 调用成本（Token 消耗）
- 需要多模态支持（文本、图片、文档统一处理）
- 需要会话感知的上下文理解

### 不适合使用

- 简单的单轮问答系统
- 对延迟要求极高（<100ms）的场景
- 完全扁平的数据（无层次结构）
- 高度网状交叉引用的数据

---

## 十、快速参考

### 配置文件（ov.conf）

```json
{
  "storage": { "workspace": "/path/to/workspace" },
  "embedding": {
    "dense": {
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "your-key",
      "provider": "volcengine",
      "dimension": 1024,
      "model": "doubao-embedding-vision-250615"
    }
  },
  "vlm": {
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "your-key",
    "provider": "volcengine",
    "model": "doubao-seed-2-0-pro-260215"
  }
}
```

### 关键参数

| 参数 | 默认值 | 说明 |
|------|-------|------|
| SCORE_PROPAGATION_ALPHA | 0.5 | 分数传播系数 |
| MAX_CONVERGENCE_ROUNDS | 3 | 递归检索收敛轮数 |
| GLOBAL_SEARCH_TOPK | 3 | 全局搜索候选数 |
| HOTNESS_ALPHA | 0.2 | 热度评分权重 |
| DIRECTORY_DOMINANCE_RATIO | 1.2 | 目录分数优势倍数 |

### 相关链接

- 官网：https://www.openviking.ai
- GitHub：https://github.com/volcengine/OpenViking
- 文档：https://www.openviking.ai/docs
