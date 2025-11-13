"""Verify FastAPI Agent setup without running the server."""

import sys
from pathlib import Path

def check_imports():
    """Check if all required modules can be imported."""
    print("=" * 60)
    print("Checking Python imports...")
    print("=" * 60)

    imports = [
        ("fastapi", "FastAPI"),
        ("httpx", "HTTP Client"),
        ("pydantic", "Data Validation"),
        ("yaml", "YAML Support"),
    ]

    all_ok = True
    for module, name in imports:
        try:
            __import__(module)
            print(f"✓ {name:20} ({module})")
        except ImportError:
            print(f"✗ {name:20} ({module}) - NOT INSTALLED")
            all_ok = False

    print()
    return all_ok


def check_project_structure():
    """Check if all required files exist."""
    print("=" * 60)
    print("Checking project structure...")
    print("=" * 60)

    required_files = [
        "fastapi_agent/__init__.py",
        "fastapi_agent/main.py",
        "fastapi_agent/agent.py",
        "fastapi_agent/llm_client.py",
        "fastapi_agent/config.py",
        "fastapi_agent/schemas/__init__.py",
        "fastapi_agent/schemas/message.py",
        "fastapi_agent/tools/__init__.py",
        "fastapi_agent/tools/base.py",
        "fastapi_agent/tools/file_tools.py",
        "fastapi_agent/tools/bash_tool.py",
        "requirements.txt",
        "README.md",
    ]

    all_ok = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} - MISSING")
            all_ok = False

    print()
    return all_ok


def check_syntax():
    """Check Python syntax by importing modules."""
    print("=" * 60)
    print("Checking Python syntax...")
    print("=" * 60)

    modules = [
        "fastapi_agent.schemas.message",
        "fastapi_agent.tools.base",
        "fastapi_agent.tools.file_tools",
        "fastapi_agent.tools.bash_tool",
        "fastapi_agent.llm_client",
        "fastapi_agent.agent",
        "fastapi_agent.config",
    ]

    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except Exception as e:
            print(f"✗ {module} - {str(e)}")
            all_ok = False

    print()
    return all_ok


def main():
    """Run all verification checks."""
    print("\n🔍 FastAPI Agent - Setup Verification\n")

    checks = [
        ("Dependencies", check_imports),
        ("Project Structure", check_project_structure),
        ("Python Syntax", check_syntax),
    ]

    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")
        if not result:
            all_passed = False

    print()

    if all_passed:
        print("✅ All checks passed! You're ready to go.")
        print()
        print("Next steps:")
        print("1. Configure your API key:")
        print("   cp fastapi_agent/config/config-example.yaml fastapi_agent/config/config.yaml")
        print("   # Edit config.yaml and add your API key")
        print()
        print("2. Start the server:")
        print("   python -m fastapi_agent.main")
        print("   # or: uvicorn fastapi_agent.main:app --reload")
        print()
        print("3. Test the API:")
        print("   python examples/test_agent.py")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print()
        print("To install dependencies:")
        print("   pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
