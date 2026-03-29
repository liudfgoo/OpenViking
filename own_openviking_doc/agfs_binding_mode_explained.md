# AGFS Binding 模式深度解析

## 1. 什么是 Binding 模式？

### 核心概念

**Binding 模式**（绑定模式/原生绑定模式）是一种**进程内调用**方式，通过**动态链接库（DLL/Shared Library）**直接调用 AGFS 的 Go 实现，而无需启动独立的 HTTP 服务器进程。

```
┌─────────────────────────────────────────────────────────────────┐
│                        两种模式的对比                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  【HTTP 模式】                        【Binding 模式】           │
│                                                                 │
│  ┌──────────────┐                   ┌──────────────────┐        │
│  │ Python 进程  │  HTTP Request     │   Python 进程    │        │
│  │              │◄────────────────►│                  │        │
│  │  AGFSClient  │   TCP/localhost   │ AGFSBindingClient│        │
│  └──────┬───────┘                   └────────┬─────────┘        │
│         │                                    │                  │
│         │ Subprocess                         │ ctypes.CDLL      │
│         │                                    │                  │
│  ┌──────▼───────┐                   ┌────────▼─────────┐        │
│  │ agfs-server  │                   │ libagfsbinding   │        │
│  │ (Go 二进制)  │                   │ (Go 编译的 DLL)  │        │
│  │  独立进程    │                   │  加载到 Python   │        │
│  └──────────────┘                   │  进程地址空间    │        │
│                                     └──────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### 技术原理

| 特性 | HTTP 模式 | Binding 模式 |
|------|-----------|--------------|
| **通信方式** | TCP HTTP 请求 | 函数调用（ctypes） |
| **进程数** | 2 个（Python + Go） | 1 个（仅 Python） |
| **延迟** | 较高（网络栈开销） | 较低（直接调用） |
| **启动速度** | 慢（需等待子进程） | 快（直接加载） |
| **部署复杂度** | 低 | 高（需要编译好的库） |
| **跨语言** | 支持（任何 HTTP 客户端） | 仅 Python |
| **调试难度** | 中等 | 高（Go 代码在 Python 进程中） |

### 为什么需要 Binding 模式？

1. **性能优化**：消除 HTTP 网络开销
2. **简化部署**：单机场景下无需管理多进程
3. **嵌入式使用**：将 AGFS 作为库嵌入到 Python 应用中
4. **测试便利**：单元测试时无需启动外部服务

---

## 2. libagfsbinding 共享库详解

### 文件类型说明

| 操作系统 | 文件扩展名 | 你的文件 |
|----------|-----------|---------|
| Linux | `.so` (Shared Object) | ❌ |
| macOS | `.dylib` (Dynamic Library) | ❌ |
| Windows | `.dll` (Dynamic Link Library) | ✅ `libagfsbinding.dll` |

**你的 `libagfsbinding.dll` 就是 Windows 版本的 AGFS Binding 库！**

### 共享库是如何生成的？

```go
// third_party/agfs/agfs-server/cmd/pybinding/main.go
// 这个文件使用 CGO 导出 C 函数

package main

/*
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
*/
import "C"

import (
    // ... Go 标准库和 AGFS 内部包
)

//export AGFS_NewClient
func AGFS_NewClient() int64 {
    return 1
}

//export AGFS_Ls
func AGFS_Ls(clientID int64, path *C.char) *C.char {
    // Go 实现读取目录
    // 返回 JSON 字符串给 Python
}

//export AGFS_Read
func AGFS_Read(clientID int64, path *C.char, offset C.int64_t, size C.int64_t, outData **C.char, outSize *C.int64_t) C.int64_t {
    // Go 实现文件读取
    // 通过指针参数返回数据
}

// ... 更多导出函数

func main() {} // 必须有但不会被调用
```

**编译命令（在 AGFS 仓库中）：**

```bash
# Linux
GOOS=linux GOARCH=amd64 CGO_ENABLED=1 go build -buildmode=c-shared -o libagfsbinding.so ./cmd/pybinding

# macOS
GOOS=darwin GOARCH=amd64 CGO_ENABLED=1 go build -buildmode=c-shared -o libagfsbinding.dylib ./cmd/pybinding

# Windows
GOOS=windows GOARCH=amd64 CGO_ENABLED=1 go build -buildmode=c-shared -o libagfsbinding.dll ./cmd/pybinding
```

---

## 3. Python 如何使用 DLL（Windows 版）

### 加载机制

```python
# openviking/pyagfs/binding_client.py

import ctypes
import platform
from pathlib import Path

def _find_library() -> str:
    """根据操作系统找到对应的共享库文件"""
    system = platform.system()
    
    if system == "Darwin":
        lib_name = "libagfsbinding.dylib"
    elif system == "Linux":
        lib_name = "libagfsbinding.so"
    elif system == "Windows":
        lib_name = "libagfsbinding.dll"  # ← 你的情况！
    else:
        raise AGFSClientError(f"Unsupported platform: {system}")
    
    # 搜索路径（按优先级）
    search_paths = [
        Path(__file__).parent / "lib" / lib_name,              # 1. pyagfs/lib/
        Path(__file__).parent.parent / "lib" / lib_name,       # 2. openviking/lib/
        Path(__file__).parent.parent.parent / "lib" / lib_name, # 3. 项目根目录/lib/
        Path("C:/Windows/System32") / lib_name,                # 4. Windows 系统目录
        Path(os.environ.get("AGFS_LIB_PATH", "")) / lib_name,  # 5. 环境变量指定
    ]
    
    for path in search_paths:
        if path and path.exists():
            return str(path)
    
    raise AGFSClientError(f"Could not find {lib_name}")
```

### 函数调用机制

```python
class BindingLib:
    """使用 ctypes 加载并包装 DLL 函数"""
    
    def _load_library(self):
        lib_path = _find_library()  # 找到 libagfsbinding.dll
        self.lib = ctypes.CDLL(lib_path)  # ← 加载 DLL
        self._setup_functions()
    
    def _setup_functions(self):
        # 告诉 ctypes 每个函数的参数和返回类型
        
        # AGFS_Ls(clientID, path) -> JSON string
        self.lib.AGFS_Ls.argtypes = [ctypes.c_int64, ctypes.c_char_p]
        self.lib.AGFS_Ls.restype = ctypes.c_char_p
        
        # AGFS_Read(clientID, path, offset, size, outData, outSize) -> errorID
        self.lib.AGFS_Read.argtypes = [
            ctypes.c_int64,           # clientID
            ctypes.c_char_p,          # path
            ctypes.c_int64,           # offset
            ctypes.c_int64,           # size
            ctypes.POINTER(ctypes.c_char_p),  # outData (输出参数)
            ctypes.POINTER(ctypes.c_int64),   # outSize (输出参数)
        ]
        self.lib.AGFS_Read.restype = ctypes.c_int64
        
        # ... 更多函数
```

### 调用流程示例

```python
# 你的 Python 代码
from openviking.pyagfs import AGFSBindingClient

# 1. 创建客户端（自动加载 libagfsbinding.dll）
client = AGFSBindingClient()

# 2. 调用 ls → 实际执行的是 DLL 中的 Go 代码
files = client.ls("/local")
```

**底层调用链：**

```
client.ls("/local")
    ↓
BindingLib.lib.AGFS_Ls(1, b"/local\x00")  # ctypes 调用
    ↓
[libagfsbinding.dll 被加载到 Python 进程内存中]
    ↓
C 函数 AGFS_Ls() 被调用（Go 编译生成）
    ↓
Go 代码执行实际的文件系统操作
    ↓
返回 JSON 字符串给 Python
```

---

## 4. Windows 下的 DLL 放置位置

### 推荐位置

```
OpenViking/
├── openviking/
│   ├── pyagfs/
│   │   ├── __init__.py
│   │   ├── binding_client.py
│   │   └── lib/
│   │       └── libagfsbinding.dll    ← 放在这里！
│   └── ...
└── ...
```

### 或者通过环境变量指定

```powershell
# PowerShell
$env:AGFS_LIB_PATH = "C:\Path\To\Your\Dll"
python your_script.py
```

```batch
:: CMD
set AGFS_LIB_PATH=C:\Path\To\Your\Dll
python your_script.py
```

### 系统级安装

将 `libagfsbinding.dll` 复制到：
- `C:\Windows\System32\`（64 位 Python）
- `C:\Windows\SysWOW64\`（32 位 Python）

---

## 5. 如何确认 DLL 是否正常加载？

### 测试代码

```python
from openviking.pyagfs import AGFSBindingClient

try:
    client = AGFSBindingClient()
    print("✅ DLL 加载成功！")
    
    # 测试基础功能
    caps = client.get_capabilities()
    print(f"AGFS 功能: {caps}")
    
    # 尝试列出根目录
    files = client.ls("/")
    print(f"根目录内容: {files}")
    
except ImportError as e:
    print(f"❌ 无法导入 AGFSBindingClient: {e}")
    
except Exception as e:
    print(f"❌ DLL 加载或调用失败: {e}")
    import traceback
    traceback.print_exc()
```

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `Could not find libagfsbinding.dll` | DLL 不在搜索路径 | 放到正确位置或设置 `AGFS_LIB_PATH` |
| `OSError: [WinError 126]` | 缺少依赖 DLL | 安装 Visual C++ Redistributable |
| `OSError: [WinError 193]` | 架构不匹配（32/64 位） | 确保 Python 和 DLL 都是 64 位 |
| `ctypes.CDLL 返回 None` | DLL 损坏 | 重新编译或下载正确的 DLL |

---

## 6. 架构总结图

```
┌────────────────────────────────────────────────────────────────┐
│                        Windows 系统                             │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐   │
│  │                    Python 进程                          │   │
│  │                                                         │   │
│  │  ┌─────────────────┐    ┌──────────────────────────┐   │   │
│  │  │  你的 Python    │    │  AGFSBindingClient       │   │   │
│  │  │  应用程序       │───►│  (openviking/pyagfs)     │   │   │
│  │  └─────────────────┘    └───────────┬──────────────┘   │   │
│  │                                     │ ctypes.CDLL      │   │
│  │                                     ▼                  │   │
│  │  ┌────────────────────────────────────────────────┐   │   │
│  │  │        libagfsbinding.dll (已加载)              │   │   │
│  │  │  ┌──────────────────────────────────────────┐  │   │   │
│  │  │  │  Go Runtime + AGFS Core (in-process)     │  │   │   │
│  │  │  │  - localfs 插件                          │  │   │   │
│  │  │  │  - memfs 插件                            │  │   │   │
│  │  │  │  - queuefs 插件                          │  │   │   │
│  │  │  └──────────────────────────────────────────┘  │   │   │
│  │  └────────────────────────────────────────────────┘   │   │
│  │                        │                               │   │
│  └────────────────────────┼───────────────────────────────┘   │
│                           │ 文件系统操作                        │
│                           ▼                                    │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              Windows 文件系统 (NTFS)                    │   │
│  │              C:\path\to\your\data                      │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. 关键结论

1. **你的 `libagfsbinding.dll` 就是 Windows 版本的 AGFS Binding 库**，功能与 Linux 的 `.so` 完全一致

2. **Binding 模式不需要启动 `agfs-server` 进程**，DLL 直接加载到 Python 进程中运行

3. **DLL 通过 ctypes 加载**，Python 代码像调用普通函数一样调用 Go 代码

4. **确保 DLL 架构与 Python 匹配**：
   - 64 位 Python → 64 位 DLL
   - 32 位 Python → 32 位 DLL

5. **如果 DLL 加载失败**，检查：
   - 文件路径是否正确
   - 是否需要 Visual C++ 运行库
   - 架构是否匹配（x64 vs x86）
