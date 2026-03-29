# OpenViking 端到端最佳实践案例

## 场景设定

**背景**：你是一个 AI 研发团队的 Tech Lead，正在搭建一个团队知识助手，帮助新成员快速上手项目。

**目标**：
- 管理技术文档（API 文档、架构设计）
- 保存项目经验（踩坑记录、最佳实践）
- 记录团队规范（代码规范、Review 标准）
- 支持新成员通过自然语言查询获取上下文

---

## 第一步：环境准备

### 1.1 创建配置文件

```bash
# 创建配置目录
mkdir -p ~/.openviking

# 创建服务端配置 ov.conf
cat > ~/.openviking/ov.conf << 'EOF'
{
  "storage": {
    "workspace": "/home/yourname/openviking_workspace"
  },
  "log": {
    "level": "INFO",
    "output": "stdout"
  },
  "embedding": {
    "dense": {
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "your-volcengine-api-key",
      "provider": "volcengine",
      "dimension": 1024,
      "model": "doubao-embedding-vision-250615"
    },
    "max_concurrent": 10
  },
  "vlm": {
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "your-volcengine-api-key",
    "provider": "volcengine",
    "model": "doubao-seed-2-0-pro-260215",
    "max_concurrent": 100
  }
}
EOF

# 创建 CLI 配置 ovcli.conf
cat > ~/.openviking/ovcli.conf << 'EOF'
{
  "url": "http://localhost:1933",
  "timeout": 60.0,
  "output": "table"
}
EOF

# 设置环境变量
export OPENVIKING_CONFIG_FILE=~/.openviking/ov.conf
export OPENVIKING_CLI_CONFIG_FILE=~/.openviking/ovcli.conf
```

---

## 第二步：准备虚拟文档数据

创建测试用的企业文档目录：

```bash
mkdir -p /tmp/openviking_demo/{docs,meetings,experiences,standards}
```

### 2.1 架构设计文档（适中规模，适合 L2）

```bash
cat > /tmp/openviking_demo/docs/architecture_payment.md << 'EOF'
# 支付系统架构设计 V2.0

## 概述
本文档描述微服务支付系统的整体架构，支持多渠道支付（微信、支付宝、银行卡）。

## 核心组件

### 1. Payment Gateway
- 职责：统一支付入口，渠道路由
- 技术：Node.js + Express，Redis 限流
- 关键配置：渠道权重、熔断阈值

### 2. Order Service
- 职责：订单生命周期管理
- 技术：Go + GORM + PostgreSQL
- 核心表：orders, order_items, refunds

### 3. Channel Adapters
- 微信支付：支持 JSAPI、Native、H5
- 支付宝：支持 PC、Mobile、Face-to-Face
- 银联：支持网关支付、快捷支付

## 数据流
1. 用户发起支付 -> Gateway 接收请求
2. Gateway 校验 -> 创建订单（Order Service）
3. 路由选择 -> 调用对应 Channel Adapter
4. 异步通知 -> 更新订单状态 -> 发送 MQ 事件

## 关键设计决策

### 幂等性保障
- 使用业务单号 + 渠道类型作为唯一键
- 数据库唯一索引防止重复订单
- Redis 分布式锁处理并发

### 对账机制
- 每日凌晨 2 点触发对账任务
- 对比平台账单与本地订单
- 差异记录进入 reconciliation_diff 表

## 踩坑记录（关键经验）
- 微信退款必须传递正确的 notify_url，否则无法收到异步通知
- 支付宝沙箱和生产的签名算法有差异，测试通过不代表生产 OK
- 订单号生成必须使用 UUID，自增 ID 在高并发下会冲突

## 性能指标
- 支付创建：P99 < 200ms
- 支付查询：P99 < 100ms
- 异步通知处理：< 500ms
EOF
```

### 2.2 API 接口文档（较小，完全适合 L2）

```bash
cat > /tmp/openviking_demo/docs/api_user_service.md << 'EOF'
# 用户服务 API 文档

## 用户注册 POST /api/v1/users

### 请求参数
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| phone | string | 是 | 手机号，11位 |
| password | string | 是 | 密码，8-20位，需包含字母和数字 |
| sms_code | string | 是 | 短信验证码，6位数字 |

### 响应示例
```json
{
  "code": 0,
  "data": {
    "user_id": "u_1234567890",
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_at": "2024-12-31T23:59:59Z"
  }
}
```

### 错误码
| 错误码 | 说明 |
|--------|------|
| 1001 | 手机号已注册 |
| 1002 | 短信验证码错误或过期 |
| 1003 | 密码强度不足 |

## 用户登录 POST /api/v1/users/login

### 请求参数
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| phone | string | 是 | 手机号 |
| password | string | 是 | 密码 |

### 安全说明
- 密码传输使用 RSA 加密
- 连续 5 次密码错误锁定账号 30 分钟
- Token 有效期 7 天，支持刷新

## 获取用户信息 GET /api/v1/users/me

### 请求头
```
Authorization: Bearer {token}
```

### 响应字段
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户唯一标识 |
| phone | string | 脱敏手机号 |
| nickname | string | 昵称 |
| avatar_url | string | 头像 URL |
| created_at | string | 注册时间 |
EOF
```

### 2.3 项目会议纪要（中等规模）

```bash
cat > /tmp/openviking_demo/meetings/sprint15_retro.md << 'EOF'
# Sprint 15 复盘会议

**时间**：2024-03-15 14:00-15:30  
**参与**：张三（Tech Lead）、李四（后端）、王五（前端）、赵六（QA）

## 本 Sprint 完成情况

### 完成项
1. ✅ 支付渠道接入 - 微信支付 JSAPI 和 H5
2. ✅ 订单状态机重构 - 解决了状态不一致问题
3. ✅ 对账系统初版 - 支持自动对账和差异标记

### 未完成项
1. ⚠️ 支付宝渠道 - 延迟到 Sprint 16（沙箱测试环境问题）
2. ⚠️ 退款自动化 - 延迟到 Sprint 17（需要法务确认流程）

## 问题与反思

### 问题 1：订单状态不一致
**现象**：用户已支付，但订单显示待支付  
**根因**：
- 微信异步通知延迟 5 分钟到达
- 用户在此期间刷新页面，触发了重复支付检查
- 并发情况下状态机转换丢失

**解决方案**：
1. 增加分布式锁（Redis RedLock）
2. 状态转换使用数据库乐观锁
3. 增加定时补偿任务，每 5 分钟扫描异常状态订单

**责任人**：李四  
**完成时间**：3 月 20 日

### 问题 2：API 响应慢
**现象**：支付创建接口 P99 达到 800ms，目标 200ms  
**根因**：
- 数据库连接池配置不当（max_open=10，太小）
- 缺少索引：orders 表按 user_id 查询慢
- 同步调用渠道接口，阻塞主线程

**解决方案**：
1. 连接池调整到 50
2. 增加复合索引 (user_id, created_at)
3. 渠道调用改为异步，使用 MQ 解耦

**性能提升**：P99 从 800ms 降到 150ms

## 经验沉淀

### 技术决策记录
**决策**：支付结果查询采用"本地优先，渠道兜底"策略  
**背景**：直接查询渠道 API 有频率限制（微信 600次/分钟）  
**方案**：
1. 先查本地数据库（缓存 5 秒）
2. 本地为处理中状态时再查渠道
3. 渠道结果异步更新本地状态

**收益**：渠道 API 调用量减少 80%

### 代码规范更新
**新增规范**：所有涉及资金的操作必须记录操作日志  
**日志内容**：操作人、操作时间、变更字段、变更前值、变更后值  
**存储**：独立 MongoDB 集合，保留 3 年

## 下 Sprint 计划

### 优先级 P0
- 支付宝渠道接入（王五负责）
- 生产环境压测（赵六负责，目标 1000 TPS）

### 优先级 P1
- 退款流程设计（需法务介入）
- 监控告警完善（支付成功率、响应时间）
EOF
```

### 2.4 踩坑记录/经验文档（小而精）

```bash
cat > /tmp/openviking_demo/experiences/redis_cluster_pitfall.md << 'EOF'
# Redis Cluster 踩坑记录：Spring Boot 连接池配置

## 问题现象
生产环境偶发 Redis 命令超时，错误信息：
```
Redis command timed out; nested exception is io.lettuce.core.RedisCommandTimeoutException
```

## 排查过程

### 第一阶段：怀疑网络问题
- telnet Redis 节点，网络正常
- 抓包发现连接建立正常，但某些命令无响应

### 第二阶段：怀疑连接池耗尽
- 监控发现连接数未达到上限
- 但出现大量 connection reset

### 根本原因
Spring Boot 2.x 默认 Lettuce 客户端的拓扑刷新配置问题：

1. Redis Cluster 节点故障转移后，客户端缓存的拓扑信息过时
2. 客户端继续向失效节点发送请求，导致超时
3. 默认拓扑刷新间隔为 60 秒，太长

## 解决方案

```yaml
spring:
  redis:
    cluster:
      nodes: 10.0.1.10:6379,10.0.1.11:6379,10.0.1.12:6379
      max-redirects: 3
    lettuce:
      cluster:
        refresh:
          adaptive: true          # 自适应刷新
          period: 10s             # 从 60s 改为 10s
      pool:
        max-active: 50
        max-idle: 20
        min-idle: 5
```

## 验证结果
- 节点故障转移后，客户端在 10 秒内感知并切换
- 超时错误从每天 200+ 次降为 0

## 经验总结
1. Redis Cluster 必须配置自适应拓扑刷新
2. 周期刷新间隔建议 5-10 秒，视业务容忍度而定
3. 监控指标：topology_refresh_delay 应 < 15 秒
EOF

cat > /tmp/openviking_demo/experiences/mysql_deadlock_analysis.md << 'EOF'
# MySQL 死锁分析与解决：订单并发扣减库存

## 业务场景
秒杀活动，多个用户同时购买同一商品，需要：
1. 扣减库存
2. 创建订单
3. 记录库存变动日志

## 死锁日志
```
LATEST DETECTED DEADLOCK
*** (1) TRANSACTION:
UPDATE products SET stock = stock - 1 WHERE id = 100
*** (1) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 58 page no 3 n bits 80 index PRIMARY

*** (2) TRANSACTION:
INSERT INTO stock_logs (product_id, change_num) VALUES (100, -1)
*** (2) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 58 page no 5 n bits 80 index `idx_product_id`
```

## 死锁原因
事务执行顺序不一致：
- 事务 A：先更新 products，再插入 stock_logs
- 事务 B：先插入 stock_logs，再更新 products

锁等待形成环路：
```
A 持有 products 锁 -> 等待 stock_logs 锁
B 持有 stock_logs 锁 -> 等待 products 锁
```

## 解决方案

### 方案 1：统一访问顺序（推荐）
所有事务按照相同顺序访问表：
1. 先操作 products
2. 再操作 stock_logs
3. 最后操作 orders

### 方案 2：乐观锁
```sql
UPDATE products 
SET stock = stock - 1 
WHERE id = 100 AND stock >= 1
```
失败时重试，适合低并发场景。

### 方案 3：库存预扣 + 异步同步
Redis 预扣库存，异步落库，彻底避免数据库锁竞争。

## 实施效果
采用方案 1 后，死锁完全消除，并发量从 50 TPS 提升到 800 TPS。
EOF
```

### 2.5 团队规范文档

```bash
cat > /tmp/openviking_demo/standards/code_review_standard.md << 'EOF'
# Code Review 规范 V1.2

## Review 流程

### 1. 提交前自检（Author）
- [ ] 单元测试通过率 100%
- [ ] 代码覆盖率 >= 80%
- [ ] lint 无错误，警告需说明原因
- [ ] 本地集成测试通过

### 2. Review 分配
- 普通需求：1 名同组工程师
- 核心模块：Tech Lead + 1 名架构组工程师
- 资金相关：必须双人 Review

### 3. Review 时效
- P0 需求：2 小时内完成
- P1 需求：24 小时内完成
- 其他：48 小时内完成

## Review Checklist

### 功能性
- [ ] 代码是否实现了需求文档的全部功能点
- [ ] 边界条件是否处理（空值、越界、超时）
- [ ] 错误处理是否完善（错误码、日志、降级策略）

### 性能
- [ ] 数据库查询是否有索引支持
- [ ] 循环内是否有 RPC/DB 调用
- [ ] 大对象是否及时释放

### 安全性
- [ ] 用户输入是否校验和转义
- [ ] 敏感操作是否有权限校验
- [ ] 日志是否脱敏（手机号、银行卡号）

### 可读性
- [ ] 命名是否清晰（函数名 <= 4 个单词）
- [ ] 复杂逻辑是否有注释说明 WHY
- [ ] 函数长度 <= 50 行

## Review 术语

| 标记 | 含义 | 处理方式 |
|------|------|---------|
| [NIT] | 小建议，非阻塞 | 作者自行决定是否修改 |
| [MUST] | 必须修改 | 修改后重新 Review |
| [QUESTION] | 疑问 | 作者回复解释 |
| [SUGGESTION] | 建议方案 | 讨论后决定是否采纳 |

## 常见问题案例

### 案例 1：魔法数字
```go
// BAD
if status == 3 {
    // ...
}

// GOOD
const OrderStatusPaid = 3
if status == OrderStatusPaid {
    // ...
}
```

### 案例 2：忽略错误
```go
// BAD
user, _ := userRepo.GetByID(ctx, userID)

// GOOD
user, err := userRepo.GetByID(ctx, userID)
if err != nil {
    return fmt.Errorf("get user %d failed: %w", userID, err)
}
```
EOF

cat > /tmp/openviking_demo/standards/git_workflow.md << 'EOF'
# Git 工作流规范

## 分支模型

```
master (生产)
  ↑
release/v1.2.0 (预发布)
  ↑
develop (开发集成)
  ↑
feature/payment-alipay (功能分支)
```

## 分支规范

### master 分支
- 只能由 release 分支合并
- 每次合并必须打 tag（格式：v1.2.0）
- 禁止直接 push

### develop 分支
- 功能分支的集成目标
- 代码必须通过 CI 才能合并

### feature 分支
- 命名：`feature/{功能简述}`
- 从 develop 切出，合并回 develop
- 生命周期：创建到合并 <= 5 个工作日

### hotfix 分支
- 命名：`hotfix/{问题简述}`
- 从 master 切出，合并回 master 和 develop
- 必须补充回归测试

## Commit Message 规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型
| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| refactor | 重构（无功能变化）|
| perf | 性能优化 |
| test | 测试相关 |
| chore | 构建/工具链 |

### 示例
```
feat(payment): 接入支付宝渠道

- 实现支付宝 PC 和 H5 支付
- 支持同步通知和异步通知
- 增加支付宝渠道单元测试

Closes #123
```

## Code Review 后的提交

### 修改后使用 fixup 提交
```bash
# 修改代码后
git add .
git commit --fixup HEAD

# 推送到远程（保持 PR 整洁）
git push origin feature/payment-alipay
```

### 合并前压缩提交
```bash
# 交互式 rebase，压缩 fixup 提交
git rebase -i --autosquash develop
```
EOF

## 第三步：启动 OpenViking 服务

```bash
# 启动服务端（后台运行）
openviking-server &

# 检查状态
ov status

# 预期输出：
# ┌─────────┬──────────┬─────────┐
# │ Status  │ Version  │ Uptime  │
# ├─────────┼──────────┼─────────┤
# │ running │ 0.2.0    │ 1m30s   │
# └─────────┴──────────┴─────────┘
```

---

## 第四步：导入资源

### 4.1 导入文档目录

```bash
# 添加技术文档
ov add-resource /tmp/openviking_demo/docs/ \
  --uri viking://resources/tech-docs \
  --wait

# 添加会议纪要
ov add-resource /tmp/openviking_demo/meetings/ \
  --uri viking://resources/meetings \
  --wait

# 添加经验沉淀
ov add-resource /tmp/openviking_demo/experiences/ \
  --uri viking://resources/experiences \
  --wait

# 添加团队规范
ov add-resource /tmp/openviking_demo/standards/ \
  --uri viking://resources/standards \
  --wait

# --wait 表示等待语义处理完成（生成 L0/L1 + 向量化）
```

### 4.2 查看资源结构

```bash
# 查看资源目录树
ov tree viking://resources/ -L 3

# 预期输出：
# viking://resources/
# ├── tech-docs/
# │   ├── .abstract.md
# │   ├── .overview.md
# │   ├── architecture_payment.md
# │   └── api_user_service.md
# ├── meetings/
# │   ├── .abstract.md
# │   ├── .overview.md
# │   └── sprint15_retro.md
# ├── experiences/
# │   ├── .abstract.md
# │   ├── .overview.md
# │   ├── redis_cluster_pitfall.md
# │   └── mysql_deadlock_analysis.md
# └── standards/
#     ├── .abstract.md
#     ├── .overview.md
#     ├── code_review_standard.md
#     └── git_workflow.md
```

### 4.3 查看 L0/L1 生成效果

```bash
# 查看技术文档的摘要（L0）
ov cat viking://resources/tech-docs/.abstract.md

# 预期输出类似：
# 支付系统架构设计文档，包含 Payment Gateway、Order Service、Channel Adapters 
# 等核心组件说明，支持微信、支付宝、银联多渠道支付，以及幂等性保障、
# 对账机制等关键设计决策。

# 查看概览（L1）
ov cat viking://resources/tech-docs/.overview.md

# 预期输出会更详细，约 1000-2000 tokens，包含：
# - 核心组件详细说明
# - 数据流描述
# - 关键设计决策
# - 踩坑记录摘要
```

---

## 第五步：检索演示

### 5.1 简单查询（find）

```bash
# 查询支付相关文档
ov find "支付渠道如何接入" --limit 5

# 预期结果：
# 1. viking://resources/tech-docs/architecture_payment.md/.overview.md [score: 0.92]
#    支付系统架构设计 V2.0，包含微信支付 JSAPI、H5、支付宝、银联等渠道...
# 
# 2. viking://resources/experiences/redis_cluster_pitfall.md/.abstract.md [score: 0.65]
#    Redis Cluster 踩坑记录...
```

### 5.2 指定范围查询

```bash
# 只在技术文档中查询
ov find "订单状态机" \
  --uri viking://resources/tech-docs \
  --limit 3

# 只在经验文档中查询
ov find "死锁" \
  --uri viking://resources/experiences
```

### 5.3 内容搜索（grep）

```bash
# 在特定目录中搜索关键词
ov grep "微信支付" \
  --uri viking://resources/tech-docs

# 预期输出：
# architecture_payment.md: 微信支付：支持 JSAPI、Native、H5
# architecture_payment.md: 微信退款必须传递正确的 notify_url
```

---

## 第六步：Python SDK 编程示例

### 6.1 基础检索脚本

创建 `demo_search.py`：

```python
#!/usr/bin/env python3
"""OpenViking 团队知识助手示例"""

import asyncio
from openviking import OpenViking

async def main():
    # 初始化客户端
    client = OpenViking()
    
    # 场景 1：新成员询问支付系统
    print("=" * 50)
    print("场景 1：新成员询问支付系统架构")
    print("=" * 50)
    
    results = await client.find(
        query="支付系统有哪些核心组件？数据流是怎样的？",
        target_uri="viking://resources/tech-docs",
        limit=3
    )
    
    print(f"找到 {results.total} 条相关上下文：\n")
    for ctx in results.resources:
        print(f"📄 {ctx.uri}")
        print(f"   类型：{ctx.level} | 分数：{ctx.score:.3f}")
        print(f"   摘要：{ctx.abstract[:150]}...\n")
    
    # 场景 2：排查生产问题
    print("=" * 50)
    print("场景 2：排查 Redis 超时问题")
    print("=" * 50)
    
    results = await client.find(
        query="Redis 连接超时 Lettuce",
        target_uri="viking://resources/experiences",
        limit=2
    )
    
    for ctx in results.resources:
        print(f"📄 {ctx.uri}")
        print(f"   摘要：{ctx.abstract}\n")
        
        # 读取详细内容（L2）
        content = await client.read_file(ctx.uri.replace('/.abstract.md', ''))
        print(f"   详细内容（前 500 字）：\n   {content[:500]}...\n")
    
    # 场景 3：查看团队规范
    print("=" * 50)
    print("场景 3：Code Review 规范")
    print("=" * 50)
    
    results = await client.find(
        query="Code Review 需要检查哪些内容？",
        target_uri="viking://resources/standards"
    )
    
    for ctx in results.resources:
        print(f"📋 {ctx.uri}")
        print(f"   {ctx.abstract}\n")

if __name__ == "__main__":
    asyncio.run(main())
```

运行：
```bash
python demo_search.py
```

### 6.2 带记忆的会话示例

创建 `demo_session.py`：

```python
#!/usr/bin/env python3
"""OpenViking 会话与记忆示例"""

import asyncio
from openviking import OpenViking, Session

async def main():
    client = OpenViking()
    
    # 创建一个带记忆的会话
    session = Session(
        client=client,
        user_id="newbie_dev_001",  # 新成员 ID
        session_id="onboarding_session_001"
    )
    
    await session.load()
    
    # 第一轮对话
    print("👤 用户：我想了解支付系统的架构")
    
    # 检索相关上下文
    results = await client.search(
        query="支付系统架构设计",
        session_info=session.get_info(),
        limit=3
    )
    
    # 记录使用的上下文
    used_uris = [ctx.uri for ctx in results.resources]
    session.used(contexts=used_uris)
    
    # 模拟 LLM 回答
    contexts = []
    for ctx in results.resources[:2]:
        content = await client.read_file(ctx.uri)
        contexts.append(content)
    
    answer = f"""根据团队文档，支付系统核心组件包括：

1. Payment Gateway：统一入口，负责渠道路由和限流
2. Order Service：订单生命周期管理  
3. Channel Adapters：对接具体支付渠道（微信、支付宝、银联）

数据来源：{', '.join(used_uris)}
"""
    
    print(f"🤖 助手：{answer}\n")
    
    session.add_message(role="user", content="我想了解支付系统的架构")
    session.add_message(role="assistant", content=answer)
    
    # 第二轮对话（利用会话上下文）
    print("👤 用户：刚才提到的渠道路由是怎么实现的？")
    
    # search() 会使用会话历史进行意图分析
    results = await client.search(
        query="Payment Gateway 渠道路由实现",
        session_info=session.get_info(),
        limit=3
    )
    
    # 这里会召回更具体的 L1/L2 内容
    print(f"🤖 助手：根据架构文档，渠道路由机制如下...\n")
    
    # 会话结束，触发记忆提取
    print("💾 会话结束，自动提取记忆...")
    await session.finalize()
    
    # 查看提取的记忆（异步写入 viking://user/{user_id}/memories）
    print("✅ 已记录用户偏好：关注支付系统、架构设计")
    print("✅ 已记录学习进度：了解支付组件 -> 渠道路由机制")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 第七步：高级功能演示

### 7.1 关系链接

```bash
# 将相关文档链接在一起
ov link \
  viking://resources/tech-docs/architecture_payment.md \
  viking://resources/experiences/redis_cluster_pitfall.md \
  --reason "支付系统使用 Redis 做限流和分布式锁"

# 查看关系
ov relations viking://resources/tech-docs/architecture_payment.md
```

### 7.2 使用树视图浏览

```bash
# 查看带摘要的目录树（Agent 友好格式）
ov tree viking://resources/ -L 2 --output agent

# 输出类似：
# 📁 tech-docs/ - 技术文档目录，包含支付系统架构、API 文档等
#   📄 architecture_payment.md - 支付系统架构设计 V2.0
#   📄 api_user_service.md - 用户服务 API 接口文档
# 📁 experiences/ - 踩坑记录和经验沉淀
#   📄 redis_cluster_pitfall.md - Redis Cluster 踩坑记录
#   📄 mysql_deadlock_analysis.md - MySQL 死锁分析
```

### 7.3 监控处理进度

```bash
# 查看语义处理队列状态
ov task list

# 如果导入大量文档，可以监控嵌入进度
watch -n 5 'ov task list --status pending'
```

---

## 第八步：最佳实践总结

### 文档组织建议

| 文档类型 | 推荐规模 | 存储位置 | 备注 |
|---------|---------|---------|------|
| 架构设计 | 10-30 页 | `tech-docs/` | L2 完全适用 |
| API 文档 | 单接口 | `tech-docs/api/` | 可拆分为单文件 |
| 会议纪要 | 原始大小 | `meetings/` | 按 Sprint 组织 |
| 踩坑记录 | 不限 | `experiences/` | 小而精最佳 |
| 团队规范 | 不限 | `standards/` | 版本化更新 |

### 检索策略建议

1. **首次查询用 `search()`**：利用会话和意图分析获得更精准结果
2. **批量查询用 `find()`**：无需 LLM 分析，延迟更低
3. **精确定位用 `grep`**：已知关键词时最快
4. **浏览用 `tree`**：获取整体结构感

### 成本控制建议

1. **写入成本**：大文档导入时批量进行，避免频繁小写入
2. **检索成本**：`find()` 比 `search()` 省一次 LLM 调用
3. **存储成本**：定期清理过期会议纪要，保留经验沉淀

---

## 完整命令速查表

```bash
# 服务管理
openviking-server           # 启动服务
ov status                   # 查看状态

# 资源管理
ov add-resource <path> --uri <uri> --wait    # 导入资源
ov rm <uri> --recursive     # 删除资源
ov mv <old_uri> <new_uri>   # 移动资源

# 检索
ov find <query> --uri <scope> --limit N      # 语义检索
ov search <query>           # 会话感知的复杂检索
ov grep <pattern> --uri <scope>              # 文本搜索
ov tree <uri> -L <depth>    # 目录浏览

# 内容读取
ov cat <uri>                # 读取内容
ov abstract <dir_uri>       # 读取 L0
ov overview <dir_uri>       # 读取 L1

# 关系管理
ov link <from> <to> --reason <desc>          # 创建关系
ov relations <uri>          # 查看关系
ov unlink <from> <to>       # 删除关系
```

---

**案例完成！** 通过这个案例，你应该掌握了：
1. ✅ 配置文件编写和服务启动
2. ✅ 多种类型文档的导入
3. ✅ L0/L1/L2 分层的效果
4. ✅ 多种检索方式的使用场景
5. ✅ Python SDK 的编程模式
6. ✅ 会话管理和记忆提取
