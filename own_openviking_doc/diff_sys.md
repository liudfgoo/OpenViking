# pyagfs 目录文件差异总结

## 概述

对比两个目录下的 `pyagfs` 模块：
- `openviking/pyagfs/`
- `third_party/agfs/agfs-sdk/python/pyagfs/`

## 文件列表对比

| 文件 | openviking/pyagfs/ | third_party/agfs/.../pyagfs/ |
|------|-------------------|------------------------------|
| `__init__.py` | 38 行 | 37 行 |
| `binding_client.py` | 638 行 | 604 行 |
| `client.py` | 1004 行 | 1000 行 |
| `exceptions.py` | 33 行 | 29 行 |
| `helpers.py` | 291 行 | 273 行 |

> 注：`openviking/pyagfs/` 目录多一个 `__pycache__` 缓存目录，这是运行时生成的，不计入源码差异。

---

## 详细差异

### 1. `__init__.py`

**差异点**：导入 `BindingFileHandle` 的写法不同

```python
# openviking/pyagfs/__init__.py (分两行)
from .binding_client import AGFSBindingClient
from .binding_client import FileHandle as BindingFileHandle

# third_party/agfs/.../pyagfs/__init__.py (一行逗号分隔)
from .binding_client import AGFSBindingClient, FileHandle as BindingFileHandle
```

**功能影响**：无差异

---

### 2. `binding_client.py`（主要差异）

| 项目 | openviking/pyagfs/ | third_party/agfs/.../pyagfs/ |
|------|-------------------|------------------------------|
| **导入顺序** | `Any, BinaryIO, Dict, Iterator, List, Optional, Union` | `List, Dict, Any, Optional, Union, Iterator, BinaryIO` |
| **`grep()` 方法** | ✅ 完整实现，调用 `AGFS_Grep` | ❌ 仅抛出 `AGFSNotSupportedError` |
| **`digest()` 方法** | 抛出 `AGFSNotSupportedError` | 抛出 `AGFSNotSupportedError` |
| **类型注解** | `-> "FileHandle":`（带引号） | `-> FileHandle:`（无引号） |
| **行数** | 638 行 | 604 行 |

**关键差异 - `grep()` 方法**：

```python
# openviking/pyagfs/binding_client.py - 已实现
def grep(self, path, pattern, recursive=False, case_insensitive=False, 
         stream=False, node_limit=None):
    if stream:
        raise AGFSNotSupportedError("Streaming not supported in binding mode")
    result = self._lib.lib.AGFS_Grep(
        self._client_id,
        path.encode("utf-8"),
        pattern.encode("utf-8"),
        1 if recursive else 0,
        1 if case_insensitive else 0,
        0,  # stream not supported
        node_limit if node_limit is not None else 0,
    )
    return self._parse_response(result)

# third_party/agfs/.../pyagfs/binding_client.py - 未实现
def grep(self, path, pattern, recursive=False, case_insensitive=False, 
         stream=False, node_limit=None):
    raise AGFSNotSupportedError("Grep not supported in binding mode")
```

**建议**：将 `openviking` 版本的 `grep()` 实现同步到 `third_party` 版本。

---

### 3. `client.py`

| 项目 | openviking/pyagfs/ | third_party/agfs/.../pyagfs/ |
|------|-------------------|------------------------------|
| **导入顺序** | `time` 在前，`requests` 在后 | `requests` 在前，`time` 在后 |
| **`_parse_ndjson_stream`** | `except json.JSONDecodeError:` | `except json.JSONDecodeError as e:` |
| **`FileHandle.__repr__`** | ✅ 有实现 | ❌ 缺失 |
| **行数** | 1004 行 | 1000 行 |

**关键差异 - `FileHandle.__repr__`**：

```python
# openviking/pyagfs/client.py - 有实现
def __repr__(self) -> str:
    status = "closed" if self._closed else "open"
    return f"FileHandle(id={self._handle_id}, path={self._path}, flags={self._flags}, {status})"

# third_party/agfs/.../pyagfs/client.py - 缺失
# 无 __repr__ 方法
```

**建议**：将 `__repr__` 方法同步到 `third_party` 版本。

---

### 4. `exceptions.py`

**差异**：代码格式差异，`third_party` 版本少了空行
- openviking: 33 行
- third_party: 29 行

**功能影响**：无差异，异常类定义完全一致。

---

### 5. `helpers.py`

**差异类型**：代码风格差异

| 项目 | openviking/pyagfs/ | third_party/agfs/.../pyagfs/ |
|------|-------------------|------------------------------|
| **导入** | 未导入 `os` | 导入了 `os`（但实际未使用） |
| **函数参数格式** | 多行格式化（每行一个参数） | 单行 |
| **字符串引号** | 双引号 `"isDir"` | 单引号 `'isDir'` |
| **字节串引号** | 双引号 `b""` | 单引号 `b''` |

**示例对比**：

```python
# openviking/pyagfs/helpers.py - 多行参数 + 双引号
def cp(
    client: "AGFSClient", src: str, dst: str, recursive: bool = False, stream: bool = False
) -> None:
    is_dir = src_info.get("isDir", False)
    data = b"".join(chunks)

# third_party/agfs/.../pyagfs/helpers.py - 单行参数 + 单引号
def cp(client: "AGFSClient", src: str, dst: str, recursive: bool = False, stream: bool = False) -> None:
    is_dir = src_info.get('isDir', False)
    data = b''.join(chunks)
```

**功能影响**：无差异

---

## 同步建议

### 需要同步的功能差异（重要）

1. **`binding_client.py` 的 `grep()` 方法**
   - 来源：`openviking/pyagfs/binding_client.py`
   - 目标：`third_party/agfs/agfs-sdk/python/pyagfs/binding_client.py`
   - 说明：`openviking` 版本已实现 `grep()` 功能，需同步到 `third_party`

2. **`client.py` 的 `FileHandle.__repr__` 方法**
   - 来源：`openviking/pyagfs/client.py`
   - 目标：`third_party/agfs/agfs-sdk/python/pyagfs/client.py`
   - 说明：添加后便于调试时查看句柄状态

### 可选同步的风格统一

- 导入语句顺序
- 字符串引号风格（单引号 vs 双引号）
- 函数参数换行格式

---

## 文件校验

两个目录的源码文件功能基本一致，主要差异在于：

1. **功能实现**：`grep()` 方法在 `openviking` 版本已实现
2. **调试支持**：`FileHandle.__repr__` 在 `openviking` 版本存在
3. **代码风格**：引号使用、换行格式等

建议优先同步功能差异，保持两个版本功能一致性。
