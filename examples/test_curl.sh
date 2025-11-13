#!/bin/bash
# Test FastAPI Agent using curl

echo "================================"
echo "FastAPI Agent - curl Test"
echo "================================"
echo ""

# Health check
echo "1. Health Check:"
curl -s http://localhost:8000/health | python3 -m json.tool
echo ""
echo ""

# List tools
echo "2. List Available Tools:"
curl -s http://localhost:8000/tools | python3 -m json.tool
echo ""
echo ""

# Run agent
echo "3. Run Agent with Task:"
curl -s -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create a Python file named test.py that prints Hello, World!",
    "max_steps": 10
  }' | python3 -m json.tool

echo ""
echo "================================"
echo "Test completed!"
echo "================================"
