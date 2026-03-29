# 代码结构：OpenViking

## 顶层目录一览

| 路径 | 类型 | 用途说明 |
|------|------|----------|
| `openviking/` | Python 源码 | 核心 Python 实现 |
| `openviking_cli/` | Python 源码 | CLI 客户端实现 |
| `bot/` | Python 源码 | VikingBot Agent 框架 |
| `crates/` | Rust 源码 | Rust CLI 工具 |
| `src/` | C++ 源码 | 核心向量索引引擎 |
| `tests/` | 测试 | 单元测试和集成测试 |
| `examples/` | 示例 | 使用示例和插件 |
| `docs/` | 文档 | 多语言文档 |
| `third_party/` | 第三方 | AGFS SDK 等依赖 |
| `build_support/` | 构建支持 | CMake 配置等 |

## 核心源码目录详解

### `openviking/` - 核心 Python 实现

> 职责：OpenViking 服务端核心逻辑，包括存储、检索、会话管理

| 子目录 | 用途 |
|--------|------|
| `core/` | 核心抽象类（Context、目录结构、Skill 加载） |
| `server/` | FastAPI HTTP 服务（路由、认证、配置） |
| `storage/` | 存储层（VikingFS、向量数据库、队列、事务） |
| `retrieve/` | 检索引擎（分层检索、意图分析） |
| `session/` | 会话管理（压缩、记忆提取、去重） |
| `service/` | 业务服务层（资源、搜索、会话、打包） |
| `resource/` | 资源处理（文件监控、调度） |
| `models/` | 模型抽象（Embedder、VLM） |
| `message/` | 消息格式定义 |
| `parse/` | 文档解析器 |
| `prompts/` | Prompt 模板 |
| `eval/` | 评估工具 |
| `telemetry/` | 遥测和监控 |
| `utils/` | 工具函数 |
| `pyagfs/` | AGFS Python SDK 包装 |

#### `openviking/core/` - 核心抽象

| 文件 | 用途 |
|------|------|
| `context.py` | `Context` 类定义，统一上下文抽象，包含 URI、level、vector 等属性 |
| `directories.py` | 目录结构初始化和管理 |
| `building_tree.py` | 构建目录树结构 |
| `skill_loader.py` | Skill 加载器 |
| `mcp_converter.py` | MCP (Model Context Protocol) 转换器 |

#### `openviking/server/` - HTTP 服务

| 文件 | 用途 |
|------|------|
| `app.py` | FastAPI 应用创建，注册路由和中间件 |
| `config.py` | 服务端配置加载和验证 |
| `auth.py` | 认证中间件 |
| `api_keys.py` | API Key 管理 |
| `identity.py` | 请求上下文和角色定义 |
| `models.py` | Pydantic 请求/响应模型 |
| `dependencies.py` | FastAPI 依赖注入 |
| `routers/` | 各模块路由实现 |

#### `openviking/storage/` - 存储层

| 文件 | 用途 |
|------|------|
| `viking_fs.py` | `VikingFS` 类，文件系统抽象层，提供 URI 到路径转换、L0/L1 读取、关系管理 |
| `vikingdb_manager.py` | `VikingDBManager` 类，向量存储管理，集成队列 |
| `viking_vector_index_backend.py` | 向量索引后端实现 |
| `collection_schemas.py` | 集合 Schema 定义 |
| `local_fs.py` | 本地文件系统适配 |
| `expr.py` | 过滤表达式 |
| `errors.py` | 存储层异常定义 |
| `transaction/` | 事务管理（锁管理器） |
| `queuefs/` | 队列文件系统（嵌入队列、语义队列） |
| `vectordb/` | 向量数据库适配 |
| `vectordb_adapters/` | 各种向量数据库适配器 |
| `observers/` | 文件变更观察者 |

#### `openviking/retrieve/` - 检索引擎

| 文件 | 用途 |
|------|------|
| `hierarchical_retriever.py` | `HierarchicalRetriever` 类，核心分层检索实现 |
| `intent_analyzer.py` | `IntentAnalyzer` 类，意图分析，生成 TypedQuery |
| `memory_lifecycle.py` | 记忆生命周期管理（热度计算） |
| `retrieval_stats.py` | 检索统计收集 |

#### `openviking/session/` - 会话管理

| 文件 | 用途 |
|------|------|
| `session.py` | `Session` 类，会话管理核心 |
| `compressor.py` | `SessionCompressor` 类，会话压缩 |
| `memory_extractor.py` | `MemoryExtractor` 类，记忆提取 |
| `memory_archiver.py` | 记忆归档 |
| `memory_deduplicator.py` | 记忆去重 |
| `tool_skill_utils.py` | 工具调用和 Skill 使用工具 |

#### `openviking/service/` - 业务服务

| 文件 | 用途 |
|------|------|
| `core.py` | `OpenVikingService` 类，主服务组合器 |
| `fs_service.py` | 文件系统服务 |
| `search_service.py` | 搜索服务 |
| `resource_service.py` | 资源服务 |
| `session_service.py` | 会话服务 |
| `relation_service.py` | 关系服务 |
| `pack_service.py` | 打包服务 |
| `debug_service.py` | 调试服务 |
| `task_tracker.py` | 任务追踪器 |

### `openviking_cli/` - CLI 客户端

> 职责：提供命令行工具和 HTTP 客户端

| 子目录 | 用途 |
|--------|------|
| `client/` | HTTP 客户端（同步/异步） |
| `session/` | 会话标识管理 |
| `retrieve/` | 检索类型定义 |
| `utils/` | 工具函数（配置、日志、URI 处理） |
| `exceptions.py` | 异常定义 |

### `bot/` - VikingBot Agent 框架

> 职责：基于 OpenViking 的 AI Agent 实现，支持多平台

| 子目录 | 用途 |
|--------|------|
| `vikingbot/agent/` | Agent 核心（上下文、记忆、技能、循环） |
| `vikingbot/channels/` | 多平台渠道适配（Telegram、Slack、Discord、飞书等） |
| `vikingbot/agent/tools/` | 工具实现（文件系统、Web、搜索、代码执行等） |
| `vikingbot/cli/` | Bot CLI 命令 |
| `vikingbot/config/` | 配置管理 |
| `vikingbot/console/` | Web 控制台（Gradio） |
| `vikingbot/cron/` | 定时任务 |
| `vikingbot/sandbox/` | 沙箱执行环境 |
| `vikingbot/providers/` | LLM 提供商适配 |
| `vikingbot/openviking_mount/` | FUSE 挂载支持 |
| `workspace/skills/` | 内置技能定义 |

### `crates/ov_cli/` - Rust CLI

> 职责：高性能 Rust CLI 实现

| 文件 | 用途 |
|------|------|
| `src/main.rs` | CLI 入口 |
| `Cargo.toml` | Rust 依赖配置 |

### `src/` - C++ 核心引擎

> 职责：高性能向量索引和检索引擎

| 子目录 | 用途 |
|--------|------|
| `index/` | 索引引擎（稠密/稀疏向量、标量索引） |
| `store/` | 存储层（KV 存储、持久化存储） |
| `common/` | 通用工具（日志、JSON、字符串处理） |
| `pybind11_interface.cpp` | Python 绑定接口 |

#### `src/index/` - 索引引擎

| 文件 | 用途 |
|------|------|
| `index_engine.cpp/h` | 索引引擎主类 |
| `index_manager.h` | 索引管理器 |
| `detail/vector/` | 向量索引实现（暴力搜索、量化、距离计算） |
| `detail/scalar/` | 标量索引（位图、范围过滤） |
| `detail/meta/` | 元数据管理 |

## 关键文件说明

### `openviking/__init__.py`
- **作用**：包入口，导出主要类
- **主要类**：`OpenViking` (别名 `SyncOpenViking`)、`AsyncOpenViking`、`Session`

### `openviking/core/context.py`
- **作用**：定义统一的 Context 数据模型
- **主要类**：`Context` - 包含 URI、level、abstract、vector、meta 等属性
- **关键概念**：`ContextLevel` (L0/L1/L2)、`ContextType` (skill/memory/resource)

### `openviking/storage/viking_fs.py`
- **作用**：OpenViking 文件系统核心，封装 AGFS 并提供语义层
- **主要类**：`VikingFS`（单例）
- **主要方法**：`read()`、`write()`、`find()`、`search()`、`abstract()`、`overview()`
- **与其他文件关系**：被所有服务调用，依赖 AGFSClient，使用 VikingDBManager

### `openviking/retrieve/hierarchical_retriever.py`
- **作用**：分层检索算法实现
- **主要类**：`HierarchicalRetriever`
- **核心算法**：`_recursive_search()` - 优先级队列驱动的目录递归检索
- **关键参数**：`SCORE_PROPAGATION_ALPHA` (0.5)、`MAX_CONVERGENCE_ROUNDS` (3)

### `openviking/service/core.py`
- **作用**：主服务类，组合所有基础设施和子服务
- **主要类**：`OpenVikingService`
- **初始化流程**：配置加载 → AGFS 启动 → 队列初始化 → 向量存储初始化

### `openviking/server/app.py`
- **作用**：FastAPI 应用创建
- **主要函数**：`create_app()`
- **注册路由**：system、admin、resources、filesystem、search、sessions 等

### `src/index/index_engine.cpp`
- **作用**：C++ 向量索引引擎核心
- **功能**：稠密向量检索、稀疏向量检索、标量过滤、混合搜索

## 入口点

| 入口类型 | 文件路径 | 说明 |
|----------|----------|------|
| 程序主入口（Server） | `openviking_cli/server_bootstrap.py` | `openviking-server` 命令 |
| CLI 入口 | `crates/ov_cli/src/main.rs` | Rust CLI `ov` 命令 |
| Python CLI 包装 | `openviking_cli/rust_cli.py` | Python 调用 Rust CLI |
| Bot 入口 | `bot/vikingbot/cli/commands.py` | `vikingbot` 命令 |
| 库的公开 API | `openviking/__init__.py` | `OpenViking`、`Session` |
| C++ 扩展入口 | `src/pybind11_interface.cpp` | Python-C++ 绑定 |

## 配置文件

| 配置文件 | 用途 |
|----------|------|
| `pyproject.toml` | Python 项目配置、依赖、脚本入口 |
| `Cargo.toml` / `crates/ov_cli/Cargo.toml` | Rust 工作空间配置 |
| `src/CMakeLists.txt` | C++ 构建配置 |
| `ov.conf` (用户配置) | 服务端运行时配置（存储、模型、日志） |
| `ovcli.conf` (用户配置) | CLI 客户端配置 |
