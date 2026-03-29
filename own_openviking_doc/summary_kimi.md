# OpenViking 设计与核心功能总结

> 基于对 README.md、examples、tests、own_openviking_doc 和 docs 的深入分析

## 一、项目概述

### 1.1 是什么

**OpenViking** 是一个专为 AI Agent 设计的开源**上下文数据库（Context Database）**，由字节跳动（ByteDance）旗下的火山引擎（Volcengine）开发并开源。

**核心定位**：
- **Agent-native**：从底层设计就考虑 Agent 的需求，而非简单的向量数据库包装
- **文件系统范式**：采用 `viking://` URI 协议，将 memories、resources、skills 统一映射为虚拟文件系统
- **分层上下文**：L0/L1/L2 三级结构，实现按需加载，显著降低 Token 消耗

### 1.2 解决的痛点

| 痛点 | 传统方案的问题 | OpenViking 的解决方案 |
|------|---------------|----------------------|
| **上下文碎片化** | Memories 在代码中，resources 在向量数据库，skills 散落在各处 | 文件系统范式统一组织，所有内容通过 URI 访问 |
| **上下文需求激增** | Agent 长时运行产生大量上下文，简单截断导致信息丢失 | L0/L1/L2 三级分层，按需加载 |
| **检索效果差** | 传统 RAG 扁平存储，缺乏全局视图 | 目录递归检索 + 语义搜索结合 |
| **不可观测性** | 检索链是黑盒，难以调试 | 可视化检索轨迹，完整保留目录浏览路径 |
| **记忆迭代受限** | 当前记忆只是用户交互记录，缺乏任务记忆 | 自动会话管理，提取长期记忆，越用越智能 |

### 1.3 与传统 RAG 的区别

**传统 RAG**：
```
文档 → 切片 → 向量数据库 → 相似度检索 → 返回片段
```

**OpenViking**：
```
资源 → 语义处理 → 文件系统存储 + 向量索引
                              ↓
                    目录递归检索（L0→L1→L2）
                              ↓
                    可视化轨迹 + 分层上下文
```

---

## 二、核心架构设计

### 2.1 整体架构

OpenViking 采用**分层模块化架构**，核心设计理念是"基础设施即服务"。

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层 (Client)                          │
│              Python SDK / Rust CLI / HTTP API                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                        服务层 (Service)                           │
│   FSService | SearchService | SessionService | ResourceService   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Retrieve      │  │    Session      │  │     Parse       │
│  (检索引擎)      │  │   (会话管理)     │  │  (上下文提取)    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        存储层 (Storage)                           │
│            AGFS (文件内容存储) + Vector Index (向量索引)            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块

| 模块 | 职责 | 关键能力 |
|------|------|----------|
| **AGFS** | 虚拟文件系统 | 提供 `viking://` 协议的存储抽象 |
| **VikingFS** | 语义层 | 管理 L0/L1/L2、关系、检索 |
| **VikingDBManager** | 向量存储 | 向量索引和队列管理 |
| **HierarchicalRetriever** | 分层检索 | 目录递归检索算法 |
| **IntentAnalyzer** | 意图分析 | LLM 分析查询意图，生成 TypedQuery |
| **SessionManager** | 会话管理 | 自动压缩和记忆提取 |
| **ResourceProcessor** | 资源处理 | 多格式文档解析（PDF/MD/HTML等）|

### 2.3 设计模式

| 模式 | 应用位置 | 说明 |
|------|---------|------|
| **单例模式** | `VikingFS`、`QueueManager` | 全局唯一实例 |
| **外观模式** | `OpenVikingService` | 封装复杂子系统，提供统一接口 |
| **策略模式** | `EmbedderBase` | 支持多种嵌入策略（Dense/Sparse/Hybrid）|
| **管道模式** | `ResourceProcessor` | 多阶段处理，支持插件扩展 |
| **观察者模式** | `WatchScheduler` | 监控资源变化，触发更新 |

---

## 三、核心功能特性

### 3.1 文件系统管理范式

采用 **viking://** URI 协议统一组织所有上下文：

```
viking://
├── resources/              # 资源：项目文档、仓库、网页等
│   ├── my_project/
│   │   ├── docs/
│   │   └── src/
│   └── ...
├── user/                   # 用户：个人偏好、习惯等
│   └── memories/
│       ├── preferences/
│       └── profile/
└── agent/                  # Agent：技能、指令、任务记忆等
    ├── skills/
    ├── memories/
    └── instructions/
```

**标准文件操作**：`ls`、`find`、`grep`、`tree`、`mv`、`rm`、`glob`

### 3.2 分层上下文加载 (L0/L1/L2)

| 层级 | 名称 | Token 限制 | 用途 |
|------|------|-----------|------|
| **L0** | Abstract | ~100 tokens | 快速相关性判断 |
| **L1** | Overview | ~2k tokens | 规划决策 |
| **L2** | Detail | 无限制 | 深度阅读 |

**示例**：
```
viking://resources/my_project/
├── .abstract.md          # L0: 一句话摘要
├── .overview.md          # L1: 核心信息和使用场景
├── docs/
│   ├── api.md            # L2: 完整内容
│   └── guide.md
└── src/
```

### 3.3 目录递归检索

**算法流程**：
```
1. 意图分析 → 生成多个 TypedQuery（1-5 个）
2. 初始定位 → 全局向量搜索定位起始目录
3. 精化探索 → 在目录内二次检索
4. 递归深入 → 如果存在子目录，递归重复
5. 结果聚合 → 返回最相关的上下文
```

**分数传播公式**：
```
final_score = α * embed_score + (1-α) * parent_score
```
其中 α = 0.5，确保深层内容继承父目录相关性

### 3.4 可视化检索轨迹

所有检索操作保留完整的目录浏览路径，便于：
- 观察检索逻辑
- 调试问题根因
- 优化检索策略

### 3.5 自动会话管理

**会话生命周期**：
```
Messages → Compress → Archive → Memory Extraction → Storage
```

**记忆分类**（6 类）：
1. **Profile**：用户基本信息
2. **Preferences**：用户偏好
3. **Entities**：实体信息
4. **Events**：事件记录
5. **Cases**：案例经验
6. **Patterns**：可复用模式

**自动提取**：会话结束时，系统自动压缩内容并提取长期记忆

---

## 四、关键数据流

### 4.1 资源写入流程

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

### 4.2 检索流程

```
用户查询
    ↓
[search() 才有] IntentAnalyzer.analyze() → TypedQuery
    ↓
Embedder.embed() → 查询向量
    ↓
HierarchicalRetriever.retrieve()
    ↓
Step 1: 确定根目录（根据 context_type）
Step 2: 全局向量搜索定位起始点
Step 3: Rerank 精排（THINKING 模式）
Step 4: 递归搜索（优先级队列）
Step 5: 分数传播 + 收敛检测
    ↓
返回 MatchedContext 列表
```

### 4.3 会话管理流程

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

---

## 五、技术栈

| 组件 | 技术 |
|------|------|
| 主要语言 | Python 3.10+ |
| CLI 工具 | Rust |
| 核心扩展 | C++ (pybind11) |
| Web 服务 | FastAPI |
| 向量检索 | 自研 C++ 索引引擎 |
| 嵌入模型 | OpenAI / Volcengine / Jina |
| VLM 模型 | OpenAI / Volcengine / LiteLLM |

---

## 六、API 概览

### 6.1 两种主要检索方式

| 特性 | `find()` | `search()` |
|------|----------|------------|
| 会话上下文 | 不需要 | 需要 |
| 意图分析 | 不使用 | LLM 分析 |
| 查询数量 | 单次 | 0-5 个 TypedQuery |
| 延迟 | 低 | 较高 |
| 适用场景 | 简单查询 | 复杂任务 |

### 6.2 核心 Python API

```python
import openviking as ov

# 初始化
client = ov.OpenViking(path="./data")  # 本地模式
# client = ov.SyncHTTPClient(url="http://localhost:1933")  # HTTP 模式

# 资源管理
client.add_resource(path="./docs", uri="viking://resources/my-docs")
client.ls("viking://resources")
client.tree("viking://resources", max_depth=2)

# 检索
results = client.find(query="支付系统设计", limit=5)
results = client.search(query="帮我创建 RFC", session=session)

# 内容读取
abstract = client.abstract(uri)   # L0
overview = client.overview(uri)   # L1
content = client.read(uri)        # L2

# 会话管理
session = client.session()
session.add_message(role="user", content="...")
session.used(contexts=[uri1, uri2])
session.commit()
```

---

## 七、应用场景

### 7.1 团队知识助手
- 管理技术文档（API 文档、架构设计）
- 保存项目经验（踩坑记录、最佳实践）
- 记录团队规范（代码规范、Review 标准）
- 新成员通过自然语言快速上手

### 7.2 Agent 记忆增强
- OpenClaw 记忆插件
- OpenCode 上下文插件
- Claude Memory Plugin

### 7.3 企业知识库
- 可观测、可调试的检索系统
- 层次化文档组织
- 多模态支持（文本、图片、视频、音频）

---

## 八、性能数据

基于 LoCoMo 长程对话测试集（1,540 案例）：

| 实验组 | 任务完成率 | 输入 Token 成本 |
|--------|-----------|----------------|
| OpenClaw（原生） | 35.65% | 24,611,530 |
| OpenClaw + LanceDB | 44.55% | 51,574,530 |
| **OpenClaw + OpenViking** | **52.08%** | **4,264,396** |

**结论**：集成 OpenViking 后，任务完成率提升 **49%**，Token 成本降低 **83%**。

---

## 九、项目现状

- **当前版本**：0.2.x（Alpha 阶段）
- **开发状态**：积极开发中，社区活跃
- **开源协议**：Apache 2.0
- **社区渠道**：Discord、飞书群、微信群

---

## 十、优势与局限

### 10.1 核心优势
1. **结构清晰**：文件系统范式直观易懂
2. **Token 高效**：分层加载减少 90%+ Token 消耗
3. **检索精准**：目录递归 + 语义搜索理解完整上下文
4. **可观测性强**：检索轨迹可视化，便于调试优化
5. **自迭代**：自动提取记忆，Agent 越用越智能

### 10.2 局限性
1. **层次化假设**：假设信息具有树形层次结构
2. **不适合完全扁平的数据**：如简单键值对存储
3. **延迟要求**：不适合 <100ms 极高延迟要求的场景

---

## 十一、相关链接

- **官网**：https://www.openviking.ai
- **GitHub**：https://github.com/volcengine/OpenViking
- **文档**：https://www.openviking.ai/docs

---

*总结日期：2026-03-27*
