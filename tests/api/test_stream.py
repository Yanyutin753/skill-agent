#!/usr/bin/env python3
"""测试 Agent API 的脚本"""

import httpx
import asyncio


async def test_agent_run():
    """测试同步 Agent API"""
    url = "http://localhost:8000/api/v1/agent/run"

    payload = {
        "message": "你好！请简单介绍一下你自己。",
    }

    print("🚀 开始测试 Agent API...")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        print(f"状态码: {response.status_code}\n")

        if response.status_code != 200:
            print(f"错误: {response.text}")
            return

        result = response.json()
        print(f"成功: {result.get('success')}")
        print(f"步骤: {result.get('steps')}")
        print(f"回复: {result.get('message')}")

    print("=" * 60)
    print("测试完成！")


async def test_stream():
    """兼容旧的函数名"""
    await test_agent_run()


if __name__ == "__main__":
    asyncio.run(test_agent_run())
