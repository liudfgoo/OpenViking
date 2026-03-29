# 科学原理：OpenViking

## 涉及的核心领域

OpenViking 的设计和实现涉及以下科学/技术领域：

1. **信息检索（Information Retrieval）**：分层检索、向量搜索、混合检索
2. **自然语言处理（NLP）**：意图分析、语义理解、文本摘要
3. **向量检索（Vector Search）**：稠密向量、稀疏向量、ANN（近似最近邻）
4. **信息论与编码**：分层上下文编码（L0/L1/L2）、熵编码思想
5. **图论与树遍历**：目录递归检索的树遍历算法

## 原理详解

### 1. 分层上下文编码（L0/L1/L2）

**问题定义**

在 AI Agent 的上下文中，如何将海量信息高效地编码，使得：
- 快速检索时能获取足够信息判断相关性（L0）
- 规划阶段能理解结构和关键点（L1）
- 执行阶段能获取完整内容（L2）
- 同时最小化 Token 消耗

**核心思想**

借鉴信息论中的**分层编码**思想，将信息按重要性分层：
- L0（Abstract）：一句话摘要，~100 tokens，用于快速相关性判断
- L1（Overview）：核心信息和使用场景，~2k tokens，用于规划决策
- L2（Detail）：完整原始内容，按需加载，用于深度阅读

**数学表述**

设原始文档为 $D$，分层编码为：

$$\text{Encode}(D) = \{L_0, L_1, L_2\}$$

其中：
- $L_0 = f_{abstract}(D)$，其中 $f_{abstract}$ 是 LLM 摘要函数
- $L_1 = f_{overview}(D)$，提取结构和关键点
- $L_2 = D$，原始内容

检索时的期望 Token 消耗：

$$E[\text{Tokens}] = p_0 \cdot |L_0| + p_1 \cdot |L_1| + p_2 \cdot |L_2|$$

其中 $p_i$ 是各层被加载的概率。由于 $p_0 \gg p_1 \gg p_2$，期望成本远低于直接加载 $L_2$。

**在代码中的体现**

- `openviking/core/context.py`：`ContextLevel` 枚举定义 L0/L1/L2
- `openviking/storage/viking_fs.py`：`abstract()` 和 `overview()` 方法读取 L0/L1
- `openviking/resource/watch_scheduler.py`：异步生成 L0/L1

---

### 2. 分层检索算法（Hierarchical Retrieval）

**问题定义**

传统向量检索的问题是：
- 扁平存储缺乏全局视图
- 难以理解信息所在的完整上下文
- 长文档切片后丢失结构信息

如何设计一个检索算法，能够：
1. 理解文档的层次结构
2. 先定位到相关目录，再精确定位内容
3. 保持检索效率和准确性

**核心思想**

**目录递归检索策略**：
1. **意图分析**：生成多个检索条件
2. **初始定位**：向量检索快速定位高相关度目录
3. **精化探索**：在目录内二次检索，更新候选集
4. **递归深入**：如果存在子目录，递归重复
5. **结果聚合**：返回最相关的上下文

**算法流程**

```
输入：查询 q，查询向量 v_q，起始目录集合 R
输出：排序的上下文列表 C

1. S ← ∅  // 候选集
2. Q ← 优先队列，初始化 (R, score=0)
3. while Q 不为空:
4.     (dir, parent_score) ← Q.pop()
5.     results ← vector_search(parent_uri=dir, query=v_q)
6.     for r in results:
7.         score ← α·r.score + (1-α)·parent_score  // 分数传播
8.         if score > threshold:
9.             S ← S ∪ {r}
10.            if r 是目录:
11.                Q.push((r.uri, score))
12.    if 收敛检测(连续3轮topk不变):
13.        break
14. return sort(S)[:limit]
```

**关键参数**

| 参数 | 值 | 说明 |
|------|-----|------|
| $\alpha$ (SCORE_PROPAGATION_ALPHA) | 0.5 | 嵌入分数与父目录分数的权重 |
| MAX_CONVERGENCE_ROUNDS | 3 | 收敛检测轮数 |
| GLOBAL_SEARCH_TOPK | 5 | 全局搜索候选数 |
| DIRECTORY_DOMINANCE_RATIO | 1.2 | 目录分数必须超过子项最大分数的倍数 |

**分数传播公式**

$$\text{final\_score}(c) = \alpha \cdot \text{embed\_score}(c) + (1-\alpha) \cdot \text{parent\_score}$$

这种传播机制确保：
- 深层内容继承父目录的相关性
- 在高相关目录中的内容更容易被召回
- 避免孤立的高分片段

**在代码中的体现**

- `openviking/retrieve/hierarchical_retriever.py`：`HierarchicalRetriever` 类
- 核心方法：`_recursive_search()`、`_global_vector_search()`、`_merge_starting_points()`

---

### 3. 意图分析与查询重写（Intent Analysis）

**问题定义**

用户的查询可能是：
- 模糊的："帮我处理这个"
- 复杂的，需要多个技能："帮我创建一个 RFC 文档并生成代码"
- 闲聊："你好"

如何理解用户意图，生成最优的检索策略？

**核心思想**

使用 LLM 进行**查询意图分析**，将自然语言查询转换为结构化的 TypedQuery：

```
用户查询 + 会话历史 → LLM 分析 → 0-5 个 TypedQuery
```

**TypedQuery 结构**

```python
@dataclass
class TypedQuery:
    query: str              # 重写后的查询
    context_type: ContextType  # MEMORY / RESOURCE / SKILL
    intent: str             # 查询目的
    priority: int           # 优先级 1-5
```

**查询风格约定**

| Context Type | 查询风格 | 示例 |
|--------------|---------|------|
| SKILL | 动词开头 | "创建 RFC 文档"、"提取 PDF 表格" |
| RESOURCE | 名词短语 | "RFC 文档模板"、"API 使用指南" |
| MEMORY | "用户的 XX" | "用户的代码风格偏好" |

**特殊处理**

- **0 个查询**：闲聊、问候，无需检索
- **多个查询**：复杂任务可能需要技能 + 资源 + 记忆

**在代码中的体现**

- `openviking/retrieve/intent_analyzer.py`：`IntentAnalyzer` 类
- Prompt 模板位于 `openviking/prompts/`

---

### 4. 混合向量检索（Hybrid Vector Retrieval）

**问题定义**

单一向量检索的局限性：
- 稠密向量：擅长语义匹配，但可能丢失关键词精确匹配
- 稀疏向量（如 BM25）：擅长关键词匹配，但缺乏语义理解

如何结合两者优势？

**核心思想**

**混合检索（Hybrid Retrieval）**：同时使用稠密向量和稀疏向量，融合两者的召回结果。

**向量表示**

- **稠密向量** $v_d \in \mathbb{R}^d$：由神经网络生成（如 text-embedding-3-large）
- **稀疏向量** $v_s \in \{0\} \cup \mathbb{R}^{|V|}$：由词汇权重组成（如 BM25、SPLADE）

**距离计算**

稠密向量（余弦相似度）：
$$\text{sim}_d(q, d) = \frac{v_q \cdot v_d}{\|v_q\| \|v_d\|}$$

稀疏向量（内积）：
$$\text{sim}_s(q, d) = \sum_{t \in q \cap d} w_{q,t} \cdot w_{d,t}$$

**融合策略**

```python
# 分别检索
dense_results = dense_index.search(query_vector, k=100)
sparse_results = sparse_index.search(sparse_vector, k=100)

# 融合（RRF - Reciprocal Rank Fusion）
for result in dense_results + sparse_results:
    score = sum(1.0 / (k + rank))  # RRF 公式
```

**在代码中的体现**

- `openviking/models/embedder/base.py`：`HybridEmbedderBase`、`CompositeHybridEmbedder`
- `src/index/detail/vector/`：稠密/稀疏向量索引实现
- `openviking/storage/viking_vector_index_backend.py`：向量搜索后端

---

### 5. 热度评分（Hotness Scoring）

**问题定义**

如何让频繁访问、最近更新的内容更容易被检索到？

**核心思想**

结合**访问频率**和**时间衰减**的热度评分机制。

**数学表述**

$$h(c) = \frac{\text{active\_count}(c)}{1 + \lambda \cdot \text{days\_since\_update}(c)}$$

或指数衰减版本：

$$h(c) = \text{active\_count}(c) \cdot e^{-\lambda \cdot \Delta t}$$

**最终分数融合**

$$\text{final\_score} = (1-\alpha) \cdot \text{semantic\_score} + \alpha \cdot h(c)$$

其中 $\alpha$ = HOTNESS_ALPHA（默认 0.2）

**在代码中的体现**

- `openviking/retrieve/memory_lifecycle.py`：`hotness_score()` 函数
- `openviking/retrieve/hierarchical_retriever.py`：`_convert_to_matched_contexts()` 中的分数融合

---

### 6. 重排序（Reranking）

**问题定义**

向量检索的初步结果可能不完全精确，如何进一步提升排序质量？

**核心思想**

使用**交叉编码器（Cross-Encoder）**进行重排序：
- 向量检索（双编码器）：快速召回候选集
- Rerank（交叉编码器）：精排前 K 个结果

**双编码器 vs 交叉编码器**

| 类型 | 计算方式 | 复杂度 | 适用阶段 |
|------|---------|--------|----------|
| 双编码器 | $\text{sim}(E_q(q), E_d(d))$ | O(n) 预计算 | 召回 |
| 交叉编码器 | $f(q, d)$ 联合编码 | O(n) 实时计算 | 精排 |

**在代码中的体现**

- `openviking/retrieve/hierarchical_retriever.py`：`_rerank_scores()` 方法
- `openviking_cli/utils/rerank.py`：`RerankClient` 类

## 与同类方法的对比

| 方法 | 优势 | 劣势 |
|------|------|------|
| **传统 RAG** | 简单直接 | 扁平存储、缺乏结构 |
| **GraphRAG** | 保留关系 | 构建成本高、复杂 |
| **OpenViking 分层检索** | 结构清晰、可观测、Token 高效 | 需要维护目录结构 |

## 局限性与假设

### 成立的前提假设

1. **层次化假设**：信息具有自然的层次结构，可以被组织为树形目录
2. **局部性假设**：相关内容在目录结构中倾向于聚集
3. **稀疏性假设**：L0/L1 足以满足大部分检索需求，L2 是稀疏访问的

### 失效场景

1. **完全扁平的数据**：如简单的键值对存储，无层次结构
2. **高度交叉引用**：内容之间存在复杂的网状关系，非树形结构
3. **超长文档**：单个文档超过 L2 处理能力，需要更细粒度切片

## 参考文献

- **分层检索**：受启发于文件系统目录遍历和 Web 搜索的层级导航
- **混合检索**：结合 Dense Retrieval (Karpukhin et al., 2020) 和 Sparse Retrieval (Robertson & Zaragoza, 2009)
- **RRF 融合**：Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"
