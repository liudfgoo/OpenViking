#!/usr/bin/env python3
"""
OpenViking 会话与记忆管理示例
展示如何使用 Session 进行多轮对话，并自动提取记忆
"""

import asyncio
from datetime import datetime
from openviking import OpenViking, Session


async def simulate_llm_response(query: str, contexts: list) -> str:
    """
    模拟 LLM 生成回答
    实际应用中，这里会调用 OpenAI/Claude 等模型
    """
    # 简单的模拟回答
    responses = {
        "支付系统": "根据团队架构文档，支付系统包含三个核心组件：\n"
                   "1. Payment Gateway - 统一入口和路由\n"
                   "2. Order Service - 订单生命周期管理\n"
                   "3. Channel Adapters - 渠道适配器",
        
        "订单状态": "订单状态机包含以下状态：\n"
                   "CREATED -> PAID -> SHIPPED -> COMPLETED\n"
                   "或 CREATED -> CANCELLED/REFUNDED",
        
        "Code Review": "根据团队规范，Review 时需要检查：\n"
                      "1. 功能性：边界条件、错误处理\n"
                      "2. 性能：索引、循环内 RPC\n"
                      "3. 安全性：输入校验、权限\n"
                      "4. 可读性：命名、注释"
    }
    
    for key, resp in responses.items():
        if key in query:
            return resp
    
    return f"基于检索到的 {len(contexts)} 条上下文，这是关于 '{query}' 的回答..."


async def session_with_memory_demo():
    """
    演示会话管理和记忆提取
    场景：新成员入职，通过与知识库对话学习
    """
    
    print("=" * 70)
    print("🎯 场景：新成员 'zhangsan' 入职，使用 OpenViking 学习团队知识")
    print("=" * 70)
    
    client = OpenViking()
    
    # 创建会话
    session = Session(
        client=client,
        user_id="zhangsan",
        session_id=f"onboarding_{datetime.now().strftime('%Y%m%d')}"
    )
    
    print(f"\n💾 会话已创建: {session.session_id}")
    print(f"   用户: {session.user_id}")
    print(f"   开始时间: {datetime.now().isoformat()}")
    
    # ========== 第一轮对话 ==========
    print("\n" + "-" * 70)
    print("💬 第一轮对话")
    print("-" * 70)
    
    user_msg1 = "我想了解支付系统的整体架构"
    print(f"\n👤 用户: {user_msg1}")
    
    # 使用 search() 进行意图感知的检索
    results = await client.search(
        query=user_msg1,
        session_info={
            "summaries": [],
            "recent_messages": []
        },
        limit=3
    )
    
    # 记录使用的上下文
    used_contexts = [ctx.uri for ctx in results.resources]
    session.used(contexts=used_contexts)
    
    # 模拟 LLM 回答
    answer1 = await simulate_llm_response(user_msg1, results.resources)
    print(f"\n🤖 助手: {answer1}")
    print(f"\n   📚 参考文档: {len(used_contexts)} 条")
    for uri in used_contexts[:2]:
        print(f"      • {uri}")
    
    # 记录到会话
    session.add_message(role="user", content=user_msg1)
    session.add_message(role="assistant", content=answer1)
    
    # ========== 第二轮对话 ==========
    print("\n" + "-" * 70)
    print("💬 第二轮对话（利用会话上下文）")
    print("-" * 70)
    
    # 用户追问 - 依赖于前文的"支付系统"
    user_msg2 = "刚才提到的订单状态机是怎么设计的？有遇到过什么问题吗？"
    print(f"\n👤 用户: {user_msg2}")
    print("   💡 这里使用了指代'刚才提到的'，需要会话上下文理解")
    
    # search() 会使用会话历史进行意图分析
    # 自动理解"订单状态机"与"支付系统"相关
    session_summary = session.get_summary() if hasattr(session, 'get_summary') else ""
    recent_msgs = [
        {"role": "user", "content": user_msg1},
        {"role": "assistant", "content": answer1}
    ]
    
    results = await client.search(
        query=user_msg2,
        session_info={
            "summaries": [session_summary] if session_summary else [],
            "recent_messages": recent_msgs
        },
        limit=3
    )
    
    # 这里应该能召回会议记录中关于订单状态问题的内容
    used_contexts = [ctx.uri for ctx in results.resources]
    session.used(contexts=used_contexts)
    
    answer2 = await simulate_llm_response(user_msg2, results.resources)
    print(f"\n🤖 助手: {answer2}")
    print(f"\n   📚 参考文档: {len(used_contexts)} 条")
    for uri in used_contexts[:2]:
        print(f"      • {uri}")
    
    session.add_message(role="user", content=user_msg2)
    session.add_message(role="assistant", content=answer2)
    
    # ========== 第三轮对话 ==========
    print("\n" + "-" * 70)
    print("💬 第三轮对话（切换话题）")
    print("-" * 70)
    
    user_msg3 = "我想知道 Code Review 需要关注哪些方面？"
    print(f"\n👤 用户: {user_msg3}")
    
    # IntentAnalyzer 应该能识别话题切换
    # 从"支付系统"切换到"团队规范"
    results = await client.search(
        query=user_msg3,
        session_info={
            "summaries": [session_summary] if session_summary else [],
            "recent_messages": recent_msgs + [
                {"role": "user", "content": user_msg2},
                {"role": "assistant", "content": answer2}
            ]
        },
        limit=3
    )
    
    used_contexts = [ctx.uri for ctx in results.resources]
    session.used(contexts=used_contexts)
    
    answer3 = await simulate_llm_response(user_msg3, results.resources)
    print(f"\n🤖 助手: {answer3}")
    
    session.add_message(role="user", content=user_msg3)
    session.add_message(role="assistant", content=answer3)
    
    # ========== 会话结束，记忆提取 ==========
    print("\n" + "-" * 70)
    print("💾 会话结束 - 自动记忆提取")
    print("-" * 70)
    
    # 统计信息
    print(f"\n📊 会话统计:")
    print(f"   总轮数: {len(session.messages) // 2}")
    print(f"   使用的上下文: {len(session._usage_records)} 条")
    
    # 提取的记忆（实际由 MemoryExtractor 异步处理）
    print(f"\n🧠 提取的用户记忆:")
    print(f"   • 关注领域: 支付系统、架构设计、团队规范")
    print(f"   • 学习进度: 了解支付组件 → 订单状态机 → Code Review")
    print(f"   • 潜在需求: 可能需要更深入的技术细节")
    
    print(f"\n🧠 提取的 Agent 经验:")
    print(f"   • 该用户偏好结构化、分步骤的解释")
    print(f"   • 善于追问具体实现细节")
    
    # 存储的记忆将写入：
    # viking://user/zhangsan/memories/preferences/learning_style
    # viking://user/zhangsan/memories/profile/interests
    
    print("\n✅ 记忆已异步保存到 viking://user/zhangsan/memories/")
    print("   下次对话时，助手将自动加载这些记忆，提供更个性化的回答")


async def memory_retrieval_demo():
    """
    演示如何利用已有记忆
    """
    
    print("\n\n" + "=" * 70)
    print("🎯 场景：第二天，'zhangsan' 再次询问，系统自动加载记忆")
    print("=" * 70)
    
    client = OpenViking()
    
    # 模拟加载用户记忆
    print("\n🧠 系统自动加载 zhangsan 的记忆:")
    print("   • 身份: 新入职后端开发工程师")
    print("   • 已了解: 支付系统架构、订单状态机")
    print("   • 学习风格: 偏好具体代码示例")
    
    # 这次查询会自动利用记忆
    query = "帮我看看这个退款代码有没有问题"
    print(f"\n👤 用户: {query}")
    print("   💡 系统根据记忆理解：用户在做支付相关开发，需要 Review 帮助")
    
    # 检索时会优先召回：
    # 1. 用户记忆中的支付系统文档
    # 2. 团队规范中的 Code Review 标准
    # 3. 踩坑记录中的相关问题
    
    results = await client.search(
        query=query,
        session_info={
            "summaries": ["用户正在开发支付系统的退款功能，之前了解过订单状态机"],
            "recent_messages": []
        },
        limit=5
    )
    
    print(f"\n🤖 助手: 基于你的背景和团队规范，我发现以下潜在问题...")
    print(f"\n   📚 优先召回的上下文:")
    for ctx in results.resources[:3]:
        print(f"      • {ctx.uri}")
    
    print("\n💡 记忆的价值:")
    print("   • 无需重复解释已知的背景")
    print("   • 自动关联相关的团队规范")
    print("   • 提供个性化的回答深度")


async def main():
    """主函数"""
    try:
        await session_with_memory_demo()
        await memory_retrieval_demo()
        
        print("\n\n" + "=" * 70)
        print("会话与记忆管理演示完成！")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        print("\n提示：此演示需要完整配置 OpenViking 服务")
        print("如服务未就绪，可以阅读代码了解设计思路")
        raise


if __name__ == "__main__":
    asyncio.run(main())
