#!/usr/bin/env python3
"""
OpenViking 基础检索示例（修正版）
参考: examples/server_client/client_async.py

运行前请确保：
1. 已安装 openviking: pip install openviking
2. 已启动 openviking-server: openviking-server &

运行方式:
    python demo_basic_search.py
    python demo_basic_search.py --url http://localhost:1933
"""

import asyncio
import argparse
import openviking as ov


async def basic_search_demo(client):
    """基础检索演示"""
    
    print("=" * 60)
    print("OpenViking 基础检索演示")
    print("=" * 60)
    
    # 演示 1: 简单检索
    print("\n📌 演示 1: 全局语义检索 'OpenViking'")
    print("-" * 60)
    
    results = await client.find(query="what is openviking", limit=3)
    
    print(f"✅ 找到 {results.total} 条相关结果：\n")
    
    # 遍历所有类型的结果（resources, memories, skills）
    all_results = list(results)
    for i, ctx in enumerate(all_results[:3], 1):
        print(f"  {i}. 📄 {ctx.uri}")
        print(f"     类型：{ctx.context_type} | 相关度：{ctx.score:.4f}")
        print(f"     摘要：{ctx.abstract[:100]}...\n")
    
    # 演示 2: 指定范围检索
    print("\n📌 演示 2: 限定范围检索")
    print("-" * 60)
    
    # 先检查有哪些资源目录
    try:
        entries = await client.ls("viking://resources", simple=True)
        print(f"可用资源目录: {entries[:5] if entries else '无'}")
        
        if entries:
            target = entries[0] if isinstance(entries[0], str) else entries[0].get("uri", "")
            if target:
                results = await client.find(
                    query="架构设计",
                    target_uri=target,
                    limit=3
                )
                print(f"\n在 '{target}' 中检索 '架构设计':")
                print(f"找到 {results.total} 条结果")
                for r in results.resources[:2]:
                    print(f"  • {r.uri} (score: {r.score:.4f})")
    except Exception as e:
        print(f"范围检索跳过: {e}")
    
    # 演示 3: 分层内容读取（L0/L1/L2）
    print("\n📌 演示 3: 分层内容读取")
    print("-" * 60)
    
    # 使用全局检索获取一个资源
    results = await client.find(query="OpenViking", limit=1)
    all_results = list(results)
    
    if all_results:
        ctx = all_results[0]
        uri = ctx.uri
        print(f"目标资源: {uri}\n")
        
        # L0: 摘要层
        try:
            abstract = await client.abstract(uri)
            print(f"📝 L0 (Abstract): {abstract[:150]}...")
        except Exception as e:
            print(f"L0 读取失败: {e}")
        
        # L1: 概览层
        try:
            overview = await client.overview(uri)
            print(f"\n📄 L1 (Overview): {overview[:200]}...")
        except Exception as e:
            print(f"L1 读取失败: {e}")
        
        # L2: 完整内容
        try:
            content = await client.read(uri)
            print(f"\n📖 L2 (Content 前300字): {content[:300]}...")
        except Exception as e:
            print(f"L2 读取失败: {e}")
    else:
        print("没有找到可读取的资源")


async def session_memory_demo(client):
    """会话与记忆演示"""
    
    print("\n\n" + "=" * 60)
    print("会话与记忆演示")
    print("=" * 60)
    
    # 创建会话
    session = client.session()
    print(f"\n📌 创建会话: {session.session_id}")
    
    # 添加消息
    await session.add_message(
        role="user",
        content="我想了解 OpenViking 的架构设计"
    )
    await session.add_message(
        role="assistant",
        content="OpenViking 采用分层架构，包括 AGFS、VikingFS、检索引擎等组件。"
    )
    print("✅ 已添加 2 条消息到会话")
    
    # 使用会话上下文进行检索
    print("\n📌 带会话上下文的检索:")
    results = await client.search(
        query="它有哪些核心组件？",
        session=session,
        limit=3
    )
    print(f"找到 {results.total} 条相关上下文")
    for r in results.resources[:2]:
        print(f"  • {r.uri} (score: {r.score:.4f})")
    
    # 提交会话（触发记忆提取）
    print("\n📌 提交会话（归档并提取记忆）...")
    commit_result = await client.commit_session(session.session_id)
    print(f"✅ 会话已提交")
    print(f"   归档状态: {'成功' if commit_result.get('archived') else '失败'}")
    print(f"   提取记忆数: {commit_result.get('memories_extracted', 0)}")
    
    # 清理会话
    await session.delete()
    print(f"\n🗑️  会话已删除: {session.session_id}")


async def filesystem_demo(client):
    """文件系统操作演示"""
    
    print("\n\n" + "=" * 60)
    print("文件系统操作演示")
    print("=" * 60)
    
    # 列出根目录
    print("\n📌 列出 viking:// 根目录:")
    entries = await client.ls("viking://")
    for entry in entries[:5]:
        if isinstance(entry, dict):
            name = entry.get("name", "?")
            is_dir = entry.get("isDir", False)
            print(f"  {'📁' if is_dir else '📄'} {name}")
        else:
            print(f"  • {entry}")
    
    # 目录树
    print("\n📌 目录树结构:")
    tree = await client.tree("viking://")
    tree_nodes = tree if isinstance(tree, list) else tree.get("children", [])
    print(f"   共 {len(tree_nodes)} 个顶级节点")
    
    # Grep 搜索
    print("\n📌 内容搜索 (grep):")
    try:
        grep_result = await client.grep(uri="viking://", pattern="OpenViking")
        grep_count = len(grep_result) if isinstance(grep_result, list) else 0
        print(f"   找到 {grep_count} 处匹配")
    except Exception as e:
        print(f"   Grep 搜索跳过: {e}")
    
    # Glob 模式匹配
    print("\n📌 文件模式匹配 (glob):")
    try:
        glob_result = await client.glob(pattern="**/*.md", uri="viking://")
        glob_count = len(glob_result) if isinstance(glob_result, list) else 0
        print(f"   找到 {glob_count} 个 .md 文件")
    except Exception as e:
        print(f"   Glob 匹配跳过: {e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="OpenViking 基础检索示例")
    parser.add_argument("--url", default="http://localhost:1933", help="Server URL")
    parser.add_argument("--api-key", default=None, help="API key")
    args = parser.parse_args()
    
    # 创建 HTTP 客户端（连接已启动的 server）
    client = ov.AsyncHTTPClient(
        url=args.url,
        api_key=args.api_key,
        timeout=60.0
    )
    
    try:
        # 初始化连接
        await client.initialize()
        print(f"✅ 已连接到 OpenViking Server: {args.url}\n")
        
        # 检查系统状态
        status = client.get_status()
        if status.get("is_healthy"):
            print("✅ 系统状态健康\n")
        else:
            print("⚠️  系统状态异常，继续执行...\n")
        
        # 执行演示
        await basic_search_demo(client)
        await filesystem_demo(client)
        await session_memory_demo(client)
        
        print("\n" + "=" * 60)
        print("所有演示完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        print("\n请检查：")
        print("1. openviking-server 是否已启动")
        print("2. 服务器地址是否正确")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
