"""Example: Test FastAPI Agent via Python client."""

import asyncio
import httpx


async def test_agent():
    """Test the agent API endpoint."""

    # Agent API endpoint
    url = "http://localhost:8000/agent/run"

    # Test task: Create a Python hello world file
    request_data = {
        "message": """
        Create a Python file named 'hello.py' that:
        1. Defines a function called greet(name)
        2. The function prints "Hello, {name}!"
        3. Calls the function with name="FastAPI Agent"
        """,
        "max_steps": 10,
    }

    print("🚀 Sending request to agent...")
    print(f"Task: {request_data['message']}\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=request_data)

        if response.status_code == 200:
            result = response.json()

            print("✅ Agent completed successfully!")
            print(f"\n📊 Stats:")
            print(f"  - Steps taken: {result['steps']}")
            print(f"  - Success: {result['success']}")

            print(f"\n💬 Agent Response:")
            print(result['message'])

            print(f"\n📋 Execution Logs:")
            for log in result['logs']:
                log_type = log.get('type')
                if log_type == 'step':
                    print(f"  Step {log['step']}/{log['max_steps']}")
                elif log_type == 'tool_call':
                    print(f"  🔧 Tool: {log['tool']}")
                elif log_type == 'tool_result':
                    status = "✓" if log['success'] else "✗"
                    print(f"  {status} Result: {log.get('content', log.get('error'))[:100]}...")
        else:
            print(f"❌ Request failed: {response.status_code}")
            print(response.text)


async def test_health():
    """Test the health endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/health")
        print("Health check:", response.json())


async def test_tools():
    """Test the tools listing endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/tools")
        result = response.json()
        print("\n📦 Available Tools:")
        for tool in result['tools']:
            print(f"  - {tool['name']}: {tool['description'][:80]}...")


if __name__ == "__main__":
    print("=" * 60)
    print("FastAPI Agent - Test Client")
    print("=" * 60)
    print("\nMake sure the server is running:")
    print("  python -m fastapi_agent.main")
    print("  or: uvicorn fastapi_agent.main:app --reload")
    print("=" * 60 + "\n")

    asyncio.run(test_health())
    asyncio.run(test_tools())
    print("\n" + "=" * 60 + "\n")
    asyncio.run(test_agent())
