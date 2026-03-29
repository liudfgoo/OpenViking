# OpenViking Agent 开发深度分析

本文档深入分析 OpenViking 在 Agent 开发中的实际运作方式，以及如何将其作为基础设施服务于自定义 Agent 开发。

---

## 一、核心问题

### 问题 1：上下文组建如何发挥作用？检索触发与执行机制

### 问题 2：OpenViking 能否作为独立基础设施服务于其他开发框架？CLI 的实际价值是什么？

---

## 二、问题 1：检索触发与执行机制

### 2.1 核心结论

检索是**半自主化**的：
- **触发条件**：大模型通过 system prompt 中的指令引导，自主决定何时调用检索工具
- **执行动作**：通过 VikingClient（HTTP 客户端）调用 OpenViking Server 的 API
- **自动化程度**：检索决策由大模型自主做出，但上下文预加载可以预先自动化

### 2.2 上下文组建：System Prompt 中的引导

在 VikingBot 的 `context.py` 中，`_get_identity()` 方法定义了系统 prompt：

```python
# bot/vikingbot/agent/context.py:186-230
def _get_identity(self, session_key: SessionKey) -> str:
    return f"""# vikingbot 🐈

You are VikingBot, an AI assistant built based on the OpenViking context database.
When acquiring information, data, and knowledge,
you **prioritize using openviking tools to read and search OpenViking
(a context database) above all other sources**.

## Memory
- Remember important facts: using openviking_memory_commit tool to commit
- Recall past events: prioritize using user_memory_search tool to search history
"""
```

**关键点**：
- 系统 prompt **明确告诉大模型**：优先使用 OpenViking 工具获取信息
- 大模型根据这个指令，在需要信息时**自主决定**调用 `openviking_search`、`user_memory_search` 等工具

### 2.3 工具的注册与定义

在 `factory.py` 中，OpenViking 功能被注册为工具：

```python
# bot/vikingbot/agent/tools/factory.py:88-97
if include_viking_tools:
    registry.register(VikingReadTool())       # openviking_read
    registry.register(VikingListTool())       # openviking_list
    registry.register(VikingSearchTool())     # openviking_search
    registry.register(VikingGrepTool())       # openviking_grep
    registry.register(VikingGlobTool())       # openviking_glob
    registry.register(VikingSearchUserMemoryTool())  # user_memory_search
    registry.register(VikingMemoryCommitTool())      # openviking_memory_commit
    registry.register(VikingAddResourceTool())       # openviking_add_resource
```

每个工具都定义了清晰的参数 schema：

```python
# bot/vikingbot/agent/tools/ov_file.py:120-166
class VikingSearchTool(OVFileTool):
    @property
    def name(self) -> str:
        return "openviking_search"

    @property
    def description(self) -> str:
        return "Search for resources in OpenViking using a query."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "target_uri": {
                    "type": "string",
                    "description": "Optional target URI to limit search scope",
                },
            },
            "required": ["query"],
        }

    async def execute(self, tool_context, query: str, target_uri: Optional[str] = "", **kwargs):
        client = await self._get_client(tool_context)
        results = await client.search(query, target_uri=target_uri)
        return str(results)
```

### 2.4 Agent Loop 中的工具执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT LOOP 流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 用户消息 → ContextBuilder.build_messages()              │
│                    ↓                                        │
│  2. 构建 System Prompt（含 Viking 记忆上下文）               │
│                    ↓                                        │
│  3. LLM 调用 → response.has_tool_calls?                     │
│                    ↓                                        │
│     ┌────────────┴────────────┐                            │
│     │ Yes                     │ No                         │
│     ↓                         ↓                            │
│  4. 解析 tool_calls      6. 返回 final_content             │
│     ↓                                                      │
│  5. ToolRegistry.execute(tool_name, arguments)             │
│     │                                                      │
│     ├─→ VikingClient.search(query, target_uri)             │
│     │      ↓                                               │
│     │   OpenViking HTTP API                                │
│     │      ↓                                               │
│     │   结果字符串化 → 添加到 messages                       │
│     │                                                      │
│     └─→ 添加 "Reflect on the results" system prompt        │
│            ↓                                               │
│       回到步骤 3（最多 50 轮迭代）                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 VikingClient：SDK 封装层

`VikingClient` 封装了 OpenViking SDK，提供统一的调用接口：

```python
# bot/vikingbot/openviking_mount/ov_server.py
class VikingClient:
    async def search(self, query: str, target_uri: Optional[str] = "") -> Dict[str, Any]:
        """搜索资源和记忆"""
        result = await self.client.search(query, target_uri=target_uri)
        return {
            "memories": [...],
            "resources": [...],
            "skills": [...],
            "total": result.total,
        }

    async def read_content(self, uri: str, level: str = "abstract") -> str:
        """读取内容（L0/L1/L2 三级）"""
        if level == "abstract":
            return await self.client.abstract(uri)
        elif level == "overview":
            return await self.client.overview(uri)
        elif level == "read":
            return await self.client.read(uri)

    async def search_memory(self, query: str, user_id: str, limit: int = 10):
        """检索用户和 Agent 记忆"""
        # 同时搜索 viking://user/{user_id}/memories/ 和
        # viking://agent/{agent_space}/memories/
```

### 2.6 记忆的自动预加载（非工具调用）

除了工具触发检索，还有**预先加载**机制：

```python
# bot/vikingbot/agent/context.py:137-147
async def build_system_prompt(self, session_key, current_message, history):
    # ...

    # Viking user profile - 自动加载用户画像
    profile = await self.memory.get_viking_user_profile(
        workspace_id=workspace_id, user_id=self._sender_id
    )
    if profile:
        parts.append(f"## Current user's information\n{profile}")
```

```python
# bot/vikingbot/agent/context.py:171-182
async def _build_user_memory(self, session_key, current_message, history):
    # Viking agent memory - 自动加载相关记忆
    viking_memory = await self.memory.get_viking_memory_context(
        current_message=current_message, workspace_id=workspace_id
    )
    if viking_memory:
        parts.append(f"## Your memories...\n{viking_memory}")
```

这里的 `get_viking_memory_context()` 内部调用了 `client.search_memory()`——**在 Agent 执行前就预先加载了相关记忆**。

### 2.7 检索触发机制总结

| 触发方式 | 时机 | 决策者 | 自动化程度 |
|---------|------|--------|-----------|
| 工具调用（openviking_search） | 大模型认为需要信息时 | 大模型自主决策 | 半自主 |
| 用户记忆预加载 | 每次 Agent 执行前 | 系统自动触发 | 完全自动 |
| Agent 记忆预加载 | 每次 Agent 执行前 | 系统自动触发 | 完全自动 |
| 会话 commit 记忆提取 | 会话结束时 | 系统自动触发 | 完全自动 |

---

## 三、问题 2：OpenViking 作为基础设施

### 3.1 核心结论

OpenViking **完全可以作为独立基础设施**，服务于任何自写 Agent：
- Python SDK (`AsyncOpenViking`, `AsyncHTTPClient`) 是面向开发者的主要接口
- HTTP API 提供了**跨语言**的支持能力
- CLI 只是最表层的使用方式，适合调试、验证和数据准备
- VikingBot 是一个**参考实现**，不是唯一的正确用法

### 3.2 架构分层：OpenViking 的多层次使用方式

```
┌──────────────────────────────────────────────────────────────┐
│                    使用方式分层                                │
├──────────────────────────────────────────────────────────────┤
│ Layer 1: CLI 命令层（ov find, ov ls, ov tree...）            │
│   → 人工操作 / 脚本调用                                        │
│   → 适合：调试、验证、数据准备                                  │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: Python SDK 层（AsyncOpenViking / SyncOpenViking）    │
│   → 自写 Agent、脚本、数据处理                                 │
│   → 适合：Python Agent 开发                                    │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: HTTP API 层（AsyncHTTPClient / SyncHTTPClient）      │
│   → 跨语言调用、远程服务                                        │
│   → 适合：任意语言 Agent 开发                                   │
├──────────────────────────────────────────────────────────────┤
│ Layer 4: OpenVikingService（内部组合器）                       │
│   → 服务端核心逻辑                                             │
│   → 适合：服务部署、二次开发                                     │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Python SDK：面向开发者的主要接口

```python
# openviking/__init__.py 暴露的公开 API
from openviking import (
    OpenViking,           # SyncOpenViking 的别名
    SyncOpenViking,       # 同步客户端（本地嵌入模式）
    AsyncOpenViking,      # 异步客户端（本地嵌入模式）
    SyncHTTPClient,       # 同步 HTTP 客户端
    AsyncHTTPClient,      # 异步 HTTP 客户端
    Session,              # 会话管理
    UserIdentifier,       # 用户标识
)
```

#### 模式 1：本地嵌入模式

```python
from openviking import AsyncOpenViking, Session

# 本地模式（嵌入进程内）
client = AsyncOpenViking(path="./ov_data")
await client.initialize()

# 检索
results = await client.find(query="性能优化", limit=5)

# 读取内容
for ctx in results.resources:
    abstract = await client.abstract(ctx.uri)   # L0
    overview = await client.overview(ctx.uri)   # L1
    content = await client.read(ctx.uri)        # L2

# 会话管理
session = client.session()
session.add_message(role="user", content="帮我分析代码")
await session.commit()  # 触发记忆提取

await client.close()
```

#### 模式 2：HTTP 客户端模式

```python
from openviking import AsyncHTTPClient

# 连接远程服务器
client = AsyncHTTPClient(
    url="http://localhost:1933",
    api_key="your-api-key",
    timeout=60.0
)
await client.initialize()

# 检索（与本地模式相同 API）
results = await client.search(query="架构设计", limit=5)

# 会话管理
session = client.session(session_id="my-session")
session.add_message(role="user", content="问题...")
await session.commit()

await client.close()
```

### 3.4 自写 Agent 使用 OpenViking 的完整示例

```python
import asyncio
from openviking import AsyncOpenViking, Session
from openai import AsyncOpenAI  # 或任何 LLM SDK

class MyCustomAgent:
    """自定义 Agent：使用 OpenViking 作为上下文基础设施"""

    def __init__(self, ov_path: str, llm_api_key: str):
        self.ov_client = AsyncOpenViking(path=ov_path)
        self.llm = AsyncOpenAI(api_key=llm_api_key)
        self.session = None

    async def initialize(self):
        """初始化"""
        await self.ov_client.initialize()
        self.session = self.ov_client.session()

    async def think(self, user_message: str) -> str:
        """处理用户消息"""

        # 1. 将用户消息加入会话
        self.session.add_message(role="user", content=user_message)

        # 2. 主动检索相关上下文（非工具调用，直接 API）
        results = await self.ov_client.search(
            query=user_message,
            session_info=self.session.get_info(),
            limit=5
        )

        # 3. 收集上下文内容（按需加载 L0 → L1 → L2）
        contexts = []
        for ctx in results.resources:
            # 先看 L0 摘要
            abstract = await self.ov_client.abstract(ctx.uri)
            if self._is_relevant(abstract, user_message):
                # 相关则加载 L1 概览
                overview = await self.ov_client.overview(ctx.uri)
                contexts.append(overview)

        # 4. 构造 prompt 并调用 LLM
        prompt = self._build_prompt(user_message, contexts)
        response = await self.llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一个助手，基于以下上下文回答问题..."},
                {"role": "user", "content": prompt}
            ]
        )

        answer = response.choices[0].message.content

        # 5. 记录响应
        self.session.add_message(role="assistant", content=answer)

        # 6. 记录使用的上下文（用于后续记忆提取）
        used_uris = [ctx.uri for ctx in results.resources]
        self.session.used(contexts=used_uris)

        return answer

    async def finish(self):
        """会话结束，触发记忆提取"""
        await self.session.commit()
        await self.ov_client.close()

    def _build_prompt(self, question: str, contexts: list[str]) -> str:
        """构造 prompt"""
        context_str = "\n\n---\n\n".join(contexts)
        return f"""基于以下上下文回答问题：

上下文：
{context_str}

问题：{question}"""

    def _is_relevant(self, abstract: str, query: str) -> bool:
        """简单相关性判断"""
        # 实际应用中可以用更复杂的逻辑
        return len(abstract) > 0


# 使用方式
async def main():
    agent = MyCustomAgent(
        ov_path="./ov_data",
        llm_api_key="your-openai-key"
    )
    await agent.initialize()

    response = await agent.think("帮我分析这个代码的性能瓶颈")
    print(response)

    await agent.finish()


if __name__ == "__main__":
    asyncio.run(main())
```

### 3.5 HTTP API：跨语言支持

OpenViking 服务端暴露了完整的 REST API（通过 FastAPI）：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/search/find` | POST | 语义检索（无会话） |
| `/api/v1/search/search` | POST | 带意图分析的检索（支持会话） |
| `/api/v1/search/grep` | POST | 文本搜索 |
| `/api/v1/search/glob` | POST | 文件模式匹配 |
| `/api/v1/fs/ls` | GET | 列出目录 |
| `/api/v1/fs/tree` | GET | 目录树 |
| `/api/v1/fs/read` | GET | 读取内容 |
| `/api/v1/fs/abstract` | GET | 读取 L0 摘要 |
| `/api/v1/fs/overview` | GET | 读取 L1 概览 |
| `/api/v1/sessions` | POST | 创建会话 |
| `/api/v1/sessions/{id}/commit` | POST | 提交会话（记忆提取） |
| `/api/v1/resources` | POST | 添加资源 |

这意味着**任何能发 HTTP 请求的语言**都可以使用 OpenViking。

### 3.6 CLI 的实际价值

CLI（`ov` 命令）**并非无用的装饰**，它在以下场景有实际价值：

| 场景 | CLI 命令 | 价值 |
|------|---------|------|
| 数据导入 | `ov add-resource ./docs/ --wait` | 快速导入文档，验证处理结果 |
| 效果验证 | `ov find "查询" --limit 5` | 验证检索效果是否符合预期 |
| 运维管理 | `ov status`、`ov task list` | 查看系统状态和任务队列 |
| 快速原型 | `ov cat viking://resources/...` | 快速测试而不需要写代码 |
| 调试 | `ov tree viking:// -L 2` | 查看目录结构，定位问题 |

但当进入**生产级的 Agent 开发**后，CLI 就退居幕后了。

### 3.7 VikingBot 的本质：参考实现

VikingBot 不是 OpenViking 的唯一正确用法。它的意义在于：

1. **可行性验证**：证明了 OpenViking 作为基础设施可以支撑完整的 Agent 系统
2. **参考实现**：展示如何将 OpenViking 集成到 Agent 框架中
3. **可直接使用**：提供了一个支持多平台（Telegram、Discord、Slack、飞书等）的 Bot 方案

但它只是一个参考实现——你完全可以：

| 组合方式 | 说明 |
|---------|------|
| OpenViking + LangChain | 使用 OpenViking 作为 LangChain 的 VectorStore 和 Memory |
| OpenViking + CrewAI | 使用 OpenViking 作为多 Agent 的共享记忆 |
| OpenViking + AutoGen | 使用 OpenViking 作为 Agent 间的上下文共享层 |
| OpenViking + 纯 asyncio | 完全自定义的轻量级 Agent |
| OpenViking + 任意 LLM SDK | 作为 RAG 应用的向量存储后端 |

### 3.8 与传统基础设施的对比

| 维度 | 数据库 (MySQL) | Redis | OpenViking |
|------|---------------|-------|-----------|
| 数据模型 | 表格 | K-V / 列表 / Hash | 虚拟文件系统 + 向量 |
| 操作接口 | SQL | Redis 命令 / SDK | Python SDK / HTTP API |
| Agent 集成 | 需要 ORM | 需要客户端 | 需要 OpenViking 客户端 |
| 自动化程度 | 无（手动查询） | 无（手动操作） | **半自动**（工具调用/预加载）|
| 数据组织 | 数据库/表/行 | 键名空间 | `viking://` 目录树 |
| 索引类型 | B+ 树 | Hash | 向量索引 + 目录结构 |
| 记忆管理 | 无 | 无 | **内置会话管理 + 记忆提取** |

**类比**：OpenViking 更像是**向量数据库 + 文件系统 + 会话管理**的融合体。它不是纯被动的存储，而是一个**支持半自动化上下文获取**的基础设施。

---

## 四、实践建议

### 4.1 何时使用 OpenViking

| 场景 | 推荐使用 | 原因 |
|------|---------|------|
| Agent 需要长期记忆 | ✅ | 内置会话管理和记忆提取 |
| 处理层次化文档 | ✅ | 目录递归检索 + L0/L1/L2 分层 |
| 需要检索可解释性 | ✅ | 可视化检索轨迹 |
| 降低 Token 成本 | ✅ | 按需加载，实测降低 80%+ |
| 简单单轮问答 | ❌ | 过于复杂，传统方案更简单 |
| 延迟要求极高 (<100ms) | ❌ | 向量检索 + LLM 处理有延迟 |
| 完全扁平数据 | ❌ | 无法利用层次结构优势 |

### 4.2 推荐的集成方式

| 场景 | 推荐方式 | 说明 |
|------|---------|------|
| Python Agent 开发 | Python SDK（本地模式） | 最简单，无需额外服务 |
| 多语言 / 远程访问 | HTTP API（服务器模式） | 跨语言，支持水平扩展 |
| 快速原型 / 验证 | CLI 命令 | 快速验证效果 |
| 生产级 Agent | VikingBot 或自定义 | 参考实现或完全自定义 |

### 4.3 关键设计决策

1. **检索触发**：决定是由大模型自主触发（工具调用），还是由代码主动触发（直接 API）
2. **上下文加载**：决定加载 L0/L1/L2 哪一层，平衡信息量和 Token 成本
3. **记忆策略**：决定何时 commit 会话，提取什么类型的记忆
4. **部署模式**：决定是本地嵌入模式还是 HTTP 服务器模式

---

## 五、关键文件参考

| 文件 | 职责 |
|------|------|
| `bot/vikingbot/agent/loop.py` | Agent Loop 核心，Think-Act-Observe 模式 |
| `bot/vikingbot/agent/context.py` | Prompt 组装，Viking 记忆集成 |
| `bot/vikingbot/agent/memory.py` | 记忆存储，Viking 记忆搜索 |
| `bot/vikingbot/agent/tools/ov_file.py` | OpenViking 工具定义 |
| `bot/vikingbot/agent/tools/factory.py` | 工具注册工厂 |
| `bot/vikingbot/openviking_mount/ov_server.py` | VikingClient SDK 封装 |
| `openviking/async_client.py` | 异步客户端（本地模式） |
| `openviking/sync_client.py` | 同步客户端包装 |
| `openviking_cli/client/base.py` | 抽象客户端接口 |
| `openviking_cli/client/http.py` | HTTP 客户端实现 |
| `openviking/server/app.py` | FastAPI HTTP 服务 |
| `openviking/service/core.py` | OpenVikingService 组合器 |
| `openviking/session/session.py` | 核心会话实现 |
