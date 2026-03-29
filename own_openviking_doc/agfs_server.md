# AGFS 与 OpenViking 关系深度分析

本文档深入分析 AGFS（Agent File System）与 OpenViking 之间的关系，以及它们在运行时的协作方式。

---

## 一、AGFS 是什么？

**AGFS (Aggregated File System / Agent File System)** 是一个独立的 Go 语言实现的**虚拟文件系统服务**。核心理念是：

> **Everything is a file, in RESTful APIs. A tribute to Plan9.**

它将各种后端服务（KV存储、消息队列、S3、SQL数据库等）**统一抽象为文件系统操作**。

### 1.1 核心思想

```
传统方式                           AGFS 方式
---------------------------------------------------------
redis.set("key", "value")    →   echo "value" > /kvfs/keys/mykey
s3.put_object(bucket, key)   →   cp file /s3fs/bucket/key
sqs.send_message(queue, msg) →   echo "msg" > /queuefs/q/enqueue
mysql.execute("SELECT ...")  →   echo "SELECT ..." > /sqlfs2/.../query
```

### 1.2 AGFS 的优势

| 优势 | 说明 |
|------|------|
| **AI 理解文件操作** | 任何 LLM 都知道如何使用 cat、echo、ls，无需 API 文档 |
| **统一接口** | 用相同方式操作所有后端，降低认知负担 |
| **可组合性** | 通过管道，重定向等 shell 特性组合服务 |
| **易于调试** | 用 ls 和 cat 就能检查系统状态 |

---

## 二、AGFS 的架构

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    AGFS Server (Go 实现)                      │
│                    监听 HTTP 端口 (默认 8080)                  │
├──────────────────────────────────────────────────────────────┤
│                     Plugin 架构                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│  │ localfs │ │  kvfs   │ │ queuefs │ │  s3fs   │ │ sqlfs   │ │
│  │ 本地目录 │ │ KV存储  │ │ 消息队列 │ │ S3 存储 │ │ 数据库  │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │  memfs  │ │heartbeat│ │ httpfs  │ │ proxyfs │ ...        │
│  │ 内存存储 │ │ 心跳监控 │ │ HTTP代理 │ │ 远程代理 │            │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘            │
├──────────────────────────────────────────────────────────────┤
│                    HTTP REST API                              │
│         /api/v1/files, /api/v1/directories, ...              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 内置插件列表

| 插件 | 挂载路径 | 功能 | 后端 |
|------|---------|------|------|
| `localfs` | `/local` | 挂载本地文件目录 | 本地磁盘 |
| `memfs` | `/memfs` | 内存文件系统 | 内存 |
| `kvfs` | `/kvfs` | Key-Value 存储 | 内存/SQLite/TiDB |
| `queuefs` | `/queuefs` | 消息队列 | 内存/SQLite/TiDB |
| `s3fs` | `/s3fs` | S3 对象存储 | Amazon S3 |
| `sqlfs` | `/sqlfs` | SQL 数据库 | SQLite/MySQL/TiDB |
| `sqlfs2` | `/sqlfs2` | SQL 数据库 V2 | SQLite/MySQL/TiDB |
| `heartbeatfs` | `/heartbeatfs` | Agent 心跳监控 | 内存 |
| `streamfs` | `/streamfs` | 流式数据（Ring Buffer） | 内存 |
| `httpfs` | `/httpfs` | HTTP 文件代理 | HTTP |
| `proxyfs` | `/proxyfs` | 远程 AGFS 代理 | HTTP |
| `serverinfofs` | `/serverinfofs` | 服务器信息 | 内存 |
| `gptfs` | `/gptfs` | GPT 文件系统 | LLM |

### 2.3 插件示例：QueueFS

消息队列被抽象为包含控制文件的目录：

```bash
agfs:/> mkdir /queuefs/tasks             # 创建队列
agfs:/> ls /queuefs/tasks
enqueue  dequeue  peek  size  clear

agfs:/> echo "job1" > /queuefs/tasks/enqueue    # 入队
019aa869-1a20-7ca6-a77a-b081e24c0593

agfs:/> cat /queuefs/tasks/size                 # 查看队列长度
1

agfs:/> cat /queuefs/tasks/dequeue              # 出队
{"id":"019aa869-...","data":"job1","timestamp":"2025-11-21T13:54:11Z"}
```

---

## 三、AGFS HTTP API

所有 API 端点都以 `/api/v1` 为前缀。

### 3.1 核心 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/files` | GET | 读取文件内容（支持 offset/size 参数） |
| `/files` | PUT | 写入文件内容 |
| `/files` | POST | 创建空文件 |
| `/files` | DELETE | 删除文件/目录 |
| `/directories` | GET | 列出目录内容 |
| `/directories` | POST | 创建目录 |
| `/stat` | GET | 获取文件元数据 |
| `/rename` | POST | 重命名/移动文件 |
| `/touch` | POST | 更新时间戳 |
| `/chmod` | POST | 修改权限 |
| `/digest` | POST | 计算文件哈希（xxh3/md5） |
| `/grep` | POST | 文件内容搜索 |
| `/health` | GET | 健康检查 |

### 3.2 插件管理 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/mounts` | GET | 列出已挂载的插件 |
| `/mount` | POST | 动态挂载插件 |
| `/unmount` | POST | 卸载插件 |
| `/plugins` | GET | 列出已加载的外部插件 |
| `/plugins/load` | POST | 加载外部插件 |
| `/plugins/unload` | POST | 卸载外部插件 |

### 3.3 使用示例

```bash
# 写入文件
curl -X PUT "http://localhost:8080/api/v1/files?path=/memfs/hello.txt" -d "Hello, AGFS!"

# 读取文件
curl "http://localhost:8080/api/v1/files?path=/memfs/hello.txt"

# 列出目录
curl "http://localhost:8080/api/v1/directories?path=/memfs"

# 创建目录
curl -X POST "http://localhost:8080/api/v1/directories?path=/memfs/test&mode=755"

# 删除文件
curl -X DELETE "http://localhost:8080/api/v1/files?path=/memfs/hello.txt"

# 动态挂载插件
curl -X POST http://localhost:8080/api/v1/mount \
  -H "Content-Type: application/json" \
  -d '{"fstype": "memfs", "path": "/temp_ram", "config": {}}'
```

---

## 四、AGFS 配置

### 4.1 配置文件结构 (config.yaml)

```yaml
server:
  address: ":8080"          # 监听地址
  log_level: "info"         # 日志级别: debug, info, warn, error

# 外部插件配置
external_plugins:
  enabled: true
  plugin_dir: "./plugins"   # 自动加载目录
  auto_load: true
  plugin_paths:             # 指定插件路径
    - "./examples/hellofs-c/hellofs-c.dylib"

# 内置插件配置
plugins:
  # 单实例配置
  memfs:
    enabled: true
    path: /memfs
    config:
      init_dirs:
        - /tmp

  # 多实例配置
  sqlfs:
    - name: local
      enabled: true
      path: /sqlfs
      config:
        backend: sqlite
        db_path: sqlfs.db

    - name: production
      enabled: true
      path: /sqlfs_prod
      config:
        backend: tidb
        dsn: "user:pass@tcp(host:4000)/db"
```

### 4.2 OpenViking 使用的 AGFS 配置

OpenViking 在运行时动态生成 AGFS 配置（`openviking/agfs_manager.py`）：

```python
def _generate_config(self) -> dict:
    config = {
        "server": {
            "address": f":{self.port}",
            "log_level": self.log_level,
        },
        "plugins": {
            "serverinfofs": {
                "enabled": True,
                "path": "/serverinfo",
                "config": {"version": "1.0.0"},
            },
            "queuefs": {
                "enabled": True,
                "path": "/queue",
            },
        },
    }

    if self.backend == "local":
        config["plugins"]["localfs"] = {
            "enabled": True,
            "path": "/local",
            "config": {
                "local_dir": str(self.vikingfs_path),
            },
        }
    elif self.backend == "s3":
        config["plugins"]["s3fs"] = {
            "enabled": True,
            "path": "/local",
            "config": {
                "bucket": self.s3_config.bucket,
                # ... S3 配置
            },
        }
    elif self.backend == "memory":
        config["plugins"]["memfs"] = {
            "enabled": True,
            "path": "/local",
        }
    return config
```

---

## 五、AGFS Python SDK

### 5.1 两种客户端

AGFS Python SDK（`pyagfs`）提供两种客户端：

#### AGFSClient（HTTP 客户端）

```python
# openviking/pyagfs/client.py
class AGFSClient:
    def __init__(self, api_base_url="http://localhost:8080", timeout=10):
        api_base_url = api_base_url.rstrip("/")
        if not api_base_url.endswith("/api/v1"):
            api_base_url = api_base_url + "/api/v1"
        self.api_base = api_base_url
        self.session = requests.Session()
        self.timeout = timeout

    def ls(self, path: str = "/") -> List[Dict]:
        response = self.session.get(
            f"{self.api_base}/directories", params={"path": path}
        )
        return response.json().get("files", [])

    def read(self, path: str, offset: int = 0, size: int = -1) -> bytes:
        params = {"path": path}
        if offset > 0:
            params["offset"] = str(offset)
        if size >= 0:
            params["size"] = str(size)
        response = self.session.get(f"{self.api_base}/files", params=params)
        return response.content

    def write(self, path: str, data: bytes) -> str:
        response = self.session.put(
            f"{self.api_base}/files", params={"path": path}, data=data
        )
        return response.json().get("message", "OK")
```

#### AGFSBindingClient（共享库客户端）

```python
# openviking/pyagfs/binding_client.py
class AGFSBindingClient:
    """直接使用共享库，无需 HTTP 服务器的客户端。

    通过 ctypes 直接调用 AGFS 实现，避免网络开销，性能更好。
    """

    def __init__(self, config_path: Optional[str] = None):
        self._lib = BindingLib()  # 加载 libagfsbinding.so/.dylib/.dll
        self._client_id = self._lib.lib.AGFS_NewClient()

    def ls(self, path: str = "/") -> List[Dict]:
        result = self._lib.lib.AGFS_Ls(self._client_id, path.encode("utf-8"))
        return self._parse_response(result).get("files", [])
```

### 5.2 辅助函数

```python
# openviking/pyagfs/helpers.py

def cp(client, src: str, dst: str, recursive: bool = False):
    """在 AGFS 内部复制文件/目录"""
    pass

def upload(client, local_path: str, remote_path: str, recursive: bool = False):
    """从本地上传到 AGFS"""
    pass

def download(client, remote_path: str, local_path: str, recursive: bool = False):
    """从 AGFS 下载到本地"""
    pass
```

---

## 六、OpenViking 如何使用 AGFS

### 6.1 架构关系

```
┌──────────────────────────────────────────────────────────────┐
│                    OpenViking 服务层                          │
│   (Python: VikingFS, VikingDBManager, Session, ...)          │
├──────────────────────────────────────────────────────────────┤
│                    VikingFS (Python 封装)                     │
│          将 viking:// URI 转换为 AGFS 路径                     │
│          提供 L0/L1 分层读取、关系管理、语义检索               │
├──────────────────────────────────────────────────────────────┤
│                    pyagfs (AGFS Python SDK)                   │
│          AGFSClient: HTTP 客户端                              │
│          AGFSBindingClient: 共享库客户端（ctypes）             │
├────────────────┬─────────────────────────────────────────────┤
│ HTTP 客户端     │ Binding 客户端（ctypes）                    │
│ 需要子进程      │ 无需子进程，Go 代码在 Python 进程内运行       │
└────────────────┴─────────────────────────────────────────────┘
```

### 6.2 AGFS 运行时模式：两种选择

OpenViking 对 AGFS 有**两种运行时模式**，取决于配置 `agfs.mode`：

#### 模式一：http-client（默认）— 需要 AGFS Server 子进程

```python
# 配置: agfs.mode = "http-client"（默认值）
from openviking import AsyncOpenViking

client = AsyncOpenViking(path="./data")
await client.initialize()  # 内部启动 agfs-server 子进程
```

在 `initialize()` 内部，`AGFSManager` 会：
1. 检查端口是否可用
2. 生成 AGFS 配置文件 (`config.yaml`)
3. **启动 `agfs-server` 子进程** (`subprocess.Popen`)
4. 等待 AGFS 服务就绪（健康检查轮询）

```python
# openviking/agfs_manager.py
class AGFSManager:
    def start(self) -> None:
        self._check_port_available()
        config_file = self._generate_config_file()
        self.process = subprocess.Popen(
            [str(self.binary_path), "-c", str(config_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._wait_for_ready()
```

#### 模式二：binding-client — 无需子进程，Go 代码直接运行在 Python 进程中

```python
# 配置: agfs.mode = "binding-client"
from openviking import AsyncOpenViking

client = AsyncOpenViking(path="./data")
await client.initialize()  # 内部加载 libagfsbinding.so，无子进程
```

这种模式下：
- **不需要**启动任何子进程
- `AGFSBindingClient` 通过 `ctypes.CDLL()` 直接加载 `libagfsbinding.so/.dylib/.dll`
- Go 实现的 AGFS 服务端代码直接运行在 Python 进程内
- `mount_agfs_backend()` 手动调用 `client.mount()` 挂载各插件（因为没有服务器来自动加载）

```
libagfsbinding.so 是什么？
  → third_party/agfs/agfs-server/cmd/pybinding/main.go
  → go build -buildmode=c-shared
  → 导出 AGFS_NewClient, AGFS_Ls, AGFS_Read 等 C-compatible 函数
  → Python ctypes 直接调用这些函数
```

#### 两种模式对比

| 维度 | http-client（默认） | binding-client |
|------|---------------------|----------------|
| AGFS Server | 独立子进程 `agfs-server` | 无（Go 代码在 Python 进程内） |
| 启动方式 | `AGFSManager.start()` 启动子进程 | `ctypes.CDLL()` 加载共享库 |
| 插件加载 | 服务器配置文件自动挂载 | `mount_agfs_backend()` 手动挂载 |
| 性能 | HTTP 网络开销 | 无网络开销，更快 |
| 部署复杂度 | 需管理子进程生命周期 | 更简单，单进程 |
| 插件动态管理 | 服务器 HTTP API | Go 共享库函数 |

#### HTTP 服务器模式

```python
from openviking import AsyncHTTPClient

client = AsyncHTTPClient(url="http://localhost:1933")
await client.initialize()
```

这种模式下，需要**手动启动** `openviking-server`，它内部会启动 AGFS（http-client 模式）。

```bash
# 手动启动 OpenViking 服务器
openviking-server
# 或
python -m openviking_cli.server_bootstrap
```

### 6.3 数据存储路径映射

当 OpenViking 存储数据时：

```
viking://resources/my_project/doc.md
        ↓
VikingFS 转换路径
        ↓
AGFS 路径: /local/resources/my_project/doc.md
        ↓
localfs 插件解析
        ↓
实际文件: {workspace}/viking/resources/my_project/doc.md
```

---

## 七、目录结构

### 7.1 third_party/agfs 结构

```
third_party/agfs/
├── agfs-server/           # Go 服务器实现
│   ├── cmd/
│   │   ├── server/main.go      # 服务器入口
│   │   └── pybinding/main.go   # Python 绑定
│   ├── pkg/
│   │   ├── config/             # 配置解析
│   │   ├── filesystem/         # 文件系统接口
│   │   ├── handlers/           # HTTP 处理器
│   │   ├── mountablefs/        # 可挂载文件系统
│   │   ├── plugin/             # 插件系统
│   │   └── plugins/            # 内置插件
│   │       ├── localfs/        # 本地文件系统
│   │       ├── memfs/          # 内存文件系统
│   │       ├── queuefs/         # 消息队列
│   │       ├── kvfs/           # KV 存储
│   │       ├── s3fs/           # S3 存储
│   │       └── ...
│   ├── Makefile
│   └── Dockerfile
├── agfs-sdk/
│   ├── go/                 # Go SDK
│   └── python/             # Python SDK (pyagfs)
│       ├── pyagfs/
│       │   ├── client.py        # HTTP 客户端
│       │   ├── binding_client.py # 共享库客户端
│       │   ├── helpers.py        # 辅助函数
│       │   └── exceptions.py     # 异常定义
│       └── pyproject.toml
├── agfs-fuse/              # FUSE 挂载支持
├── agfs-shell/             # 交互式 shell
├── agfs-mcp/               # MCP 协议支持
└── README.md
```

### 7.2 openviking/pyagfs 结构

```
openviking/pyagfs/
├── __init__.py             # 包入口，导出主要类
├── client.py               # AGFSClient HTTP 客户端
├── binding_client.py       # AGFSBindingClient 共享库客户端
├── helpers.py              # cp/upload/download 辅助函数
└── exceptions.py           # 异常定义
```

**关键事实**：`openviking/pyagfs/` 是从 `third_party/agfs/agfs-sdk/python/pyagfs/` **复制**的，用于让 OpenViking 可以直接导入 AGFS 客户端而无需单独安装 agfs-sdk。

### 7.3 openviking/bin 结构

```
openviking/bin/
├── agfs-server            # Linux/macOS AGFS 服务器二进制
├── agfs-server.exe       # Windows AGFS 服务器二进制
└── libagfsbinding.*       # Python 绑定共享库
```

---

## 八、完整的运行时架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户应用                                    │
│            (自写 Agent / VikingBot / CLI)                           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    OpenViking Python SDK                             │
│  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐ │
│  │ AsyncOpenViking   │  │ AsyncHTTPClient   │  │ SyncOpenViking  │ │
│  │ (本地嵌入模式)     │  │ (HTTP 服务器模式)  │  │ (同步包装)      │ │
│  └─────────┬─────────┘  └─────────┬─────────┘  └────────┬────────┘ │
│            │                      │                     │          │
│            ▼                      │                     │          │
│  ┌───────────────────┐            │                     │          │
│  │ LocalClient       │            │                     │          │
│  │ (封装 OpenViking  │            │                     │          │
│  │  Service)         │            │                     │          │
│  └─────────┬─────────┘            │                     │          │
└────────────┼───────────────────────┼─────────────────────┼──────────┘
             │                       │                     │
             ▼                       │                     ▼
┌────────────────────────────────────┼───────────────────────────────┐
│       OpenVikingService (Python)    │                               │
│  ┌─────────────────────────────────┐│┌───────────────────────────┐ │
│  │ VikingFS (viking:// URI, L0/L1)  │││ VikingDBManager           │ │
│  │ SessionService (会话管理)        │││ SessionService            │ │
│  └─────────────────────────────────┘│└───────────────────────────┘ │
└──────────────────────────┬──────────┴────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    pyagfs (AGFS Python SDK)                         │
│  ┌───────────────────┐          ┌─────────────────────┐            │
│  │ AGFSClient        │          │ AGFSBindingClient   │            │
│  │ (HTTP REST API)   │          │ (ctypes 共享库)     │            │
│  └─────────┬─────────┘          └─────────┬───────────┘            │
└────────────┼─────────────────────────────────┼─────────────────────┘
             │                               │
     ┌───────┴───────┐                       │ ctypes 调用
     │ HTTP 请求      │                       │ (无网络)
     │ :8080         │                       ▼
     ▼               ▼         ┌──────────────────────────────┐
┌──────────────────────────┐   │  libagfsbinding.so/.dll/.dylib  │
│   AGFS Server (Go 子进程) │   │  ┌────────────────────────┐  │
│   ┌────────────────────┐ │   │  │ Go AGFS 服务端实现      │  │
│   │ agfs-server        │ │   │  │ 运行在 Python 进程内    │  │
│   │ (独立进程, HTTP)   │ │   │  │ Plugins: localfs,kvfs.. │  │
│   └────────────────────┘ │   │  └────────────────────────┘  │
└──────────┬─────────────────┘   └──────────────┬───────────────┘
           │                                   │
           ▼                                   ▼
     ┌──────────┐                       ┌──────────┐
     │ 本地磁盘   │                       │ 本地磁盘   │
     │ S3/KV/...│                       │ S3/KV/...│
     └──────────┘                       └──────────┘

        http-client 模式                  binding-client 模式
     （需要子进程）                  （无需子进程，性能更好）
```

---

## 九、总结

### 9.1 关键问题解答

| 问题 | 答案 |
|------|------|
| OpenViking 运行时必须启动 AGFS Server 吗？ | **不一定**：http-client 模式需要，binding-client 模式不需要 |
| http-client 模式 | `AGFSManager.start()` 自动启动 `agfs-server` 子进程 |
| binding-client 模式 | 无需子进程，`ctypes.CDLL()` 加载 `libagfsbinding`，Go 代码直接在 Python 进程内运行 |
| HTTP 模式如何启动 AGFS？ | `openviking-server` 内部启动 AGFS（http-client 模式）|
| `third_party/agfs` 的作用 | 提供完整的 AGFS Go 实现、Python SDK 和 ctypes 绑定源码 |
| `openviking/pyagfs` 的作用 | 复制自 agfs-sdk，作为 OpenViking 的内置依赖 |
| AGFS binary 在哪里？ | `openviking/bin/agfs-server(.exe)` |
| 数据实际存储在哪里？ | `{workspace}/viking/` 目录下（由 localfs 插件管理） |

### 9.2 AGFS vs 传统方案对比

| 维度 | 传统方案 | AGFS |
|------|---------|------|
| 接口统一性 | 每个服务有不同 API | 统一文件操作接口 |
| AI 可理解性 | 需要学习 API 文档 | LLM 原生理解文件操作 |
| 可组合性 | 各服务独立 | 支持管道，重定向 |
| 调试难度 | 需要专门工具 | 用 ls/cat 即可 |
| 扩展性 | 需要修改代码 | 插件化架构 |

### 9.3 相关文件参考

| 文件 | 职责 |
|------|------|
| `third_party/agfs/agfs-server/cmd/server/main.go` | AGFS 服务器入口 |
| `third_party/agfs/agfs-server/pkg/plugins/*/` | 各种插件实现 |
| `third_party/agfs/agfs-sdk/python/pyagfs/` | 原始 Python SDK |
| `openviking/pyagfs/` | 复制的 Python SDK |
| `openviking/agfs_manager.py` | AGFS 子进程生命周期管理 |
| `openviking/storage/viking_fs.py` | VikingFS 封装层 |
| `openviking/bin/agfs-server` | AGFS 服务器二进制 |
