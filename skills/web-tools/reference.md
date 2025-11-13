# Web Tools - Advanced Reference

## Advanced httpx Usage

### Session Management
```python
import httpx

# Persistent session with connection pooling
with httpx.Client() as client:
    client.headers.update({"User-Agent": "MyApp/1.0"})

    response1 = client.get("https://api.example.com/endpoint1")
    response2 = client.get("https://api.example.com/endpoint2")
```

### Custom Authentication
```python
import httpx
from httpx import Auth

class BearerAuth(Auth):
    def __init__(self, token):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request

# Use custom auth
client = httpx.Client(auth=BearerAuth("your-token"))
```

### Streaming Responses
```python
with httpx.stream("GET", "https://example.com/large-file") as response:
    for chunk in response.iter_bytes(chunk_size=8192):
        process_chunk(chunk)
```

## Advanced Web Scraping

### JavaScript-rendered Pages
For pages that require JavaScript, you'll need additional tools:

```bash
# Install playwright for browser automation
uv pip install playwright
playwright install chromium
```

```python
from playwright.async_api import async_playwright

async def scrape_dynamic_page(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)

        # Wait for content to load
        await page.wait_for_selector(".content")

        # Extract content
        content = await page.inner_text(".content")

        await browser.close()
        return content
```

### Handling CAPTCHA and Anti-bot
- Use delays and random intervals
- Rotate user agents
- Use proxy servers
- Implement retry logic with exponential backoff

## GraphQL APIs

### Query GraphQL Endpoints
```python
import httpx

def query_graphql(url, query, variables=None):
    payload = {
        "query": query,
        "variables": variables or {}
    }

    response = httpx.post(url, json=payload)
    return response.json()

# Example query
query = """
query GetUser($id: ID!) {
    user(id: $id) {
        name
        email
    }
}
"""

result = query_graphql(
    "https://api.example.com/graphql",
    query,
    {"id": "123"}
)
```

## WebSocket Connections

### Real-time Data with WebSockets
```python
import asyncio
import websockets

async def connect_websocket(url):
    async with websockets.connect(url) as websocket:
        # Send message
        await websocket.send("Hello")

        # Receive messages
        async for message in websocket:
            print(f"Received: {message}")
```

## Performance Optimization

### Parallel Requests
```python
import asyncio
import httpx

async def fetch_all(urls):
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.json() for r in responses]

# Fetch multiple URLs concurrently
urls = ["https://api.example.com/1", "https://api.example.com/2"]
results = asyncio.run(fetch_all(urls))
```

### Caching with TTL
```python
from datetime import datetime, timedelta
import httpx

class CachedClient:
    def __init__(self, ttl_seconds=300):
        self.cache = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get(self, url):
        now = datetime.now()

        if url in self.cache:
            data, timestamp = self.cache[url]
            if now - timestamp < self.ttl:
                return data

        response = httpx.get(url)
        self.cache[url] = (response.json(), now)
        return response.json()
```

## Security Best Practices

### Secure API Keys
Never hardcode API keys:

```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("API_KEY")
```

### Validate SSL Certificates
```python
import httpx

# Verify SSL (default behavior)
response = httpx.get("https://secure-api.com")

# Disable SSL verification (NOT recommended for production)
response = httpx.get("https://api.com", verify=False)
```

### Input Validation
```python
from urllib.parse import urlparse

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False
```

## Monitoring and Logging

### Request Logging
```python
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def logged_request(url):
    logger.info(f"Requesting: {url}")
    try:
        response = httpx.get(url)
        logger.info(f"Response: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
```

### Retry with Exponential Backoff
```python
import time
import httpx

def fetch_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = httpx.get(url, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            time.sleep(wait_time)
```
