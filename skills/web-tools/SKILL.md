---
name: web-tools
description: Web scraping, API interaction, and HTTP request tools for fetching and processing web content
license: MIT
allowed-tools: ["bash_tool", "read_file", "write_file"]
---

# Web Tools Skill

## Overview

This skill provides guidance for web-related operations including:
- Making HTTP requests with `curl` or `httpx`
- Web scraping with BeautifulSoup
- API interaction and JSON processing
- Data extraction and transformation

## Quick Start with curl

### Simple GET Request
```bash
curl https://api.example.com/data
```

### GET with Headers
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     https://api.example.com/protected
```

### POST Request with JSON
```bash
curl -X POST https://api.example.com/create \
     -H "Content-Type: application/json" \
     -d '{"name": "test", "value": 123}'
```

### Save Response to File
```bash
curl -o output.json https://api.example.com/data
```

## Python HTTP Requests with httpx

### Installation
```bash
# Install httpx in the workspace
uv pip install httpx beautifulsoup4 lxml
```

### Basic GET Request
```python
import httpx

response = httpx.get("https://api.example.com/data")
print(response.json())
```

### Async HTTP Requests
```python
import asyncio
import httpx

async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()

data = asyncio.run(fetch_data())
```

### POST with Authentication
```python
import httpx

headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
}

data = {"name": "test", "value": 123}

response = httpx.post(
    "https://api.example.com/create",
    headers=headers,
    json=data
)

print(response.status_code)
print(response.json())
```

## Web Scraping with BeautifulSoup

### Parse HTML
```python
from bs4 import BeautifulSoup
import httpx

# Fetch webpage
response = httpx.get("https://example.com")
html = response.text

# Parse HTML
soup = BeautifulSoup(html, "lxml")

# Extract title
title = soup.find("title").text
print(f"Page title: {title}")

# Find all links
links = soup.find_all("a")
for link in links:
    href = link.get("href")
    text = link.text
    print(f"{text}: {href}")
```

### Extract Table Data
```python
from bs4 import BeautifulSoup

# Parse HTML table
table = soup.find("table")
rows = table.find_all("tr")

data = []
for row in rows:
    cols = row.find_all("td")
    cols = [col.text.strip() for col in cols]
    data.append(cols)

# Convert to CSV
import csv
with open("table_data.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(data)
```

### Extract Specific Elements
```python
# Find by CSS class
articles = soup.find_all("div", class_="article")

# Find by ID
header = soup.find(id="main-header")

# Find by attribute
links = soup.find_all("a", attrs={"target": "_blank"})

# Use CSS selectors
items = soup.select("div.container > p.text")
```

## API Best Practices

### Error Handling
```python
import httpx

try:
    response = httpx.get("https://api.example.com/data", timeout=10.0)
    response.raise_for_status()  # Raise exception for 4xx/5xx
    data = response.json()
except httpx.HTTPStatusError as e:
    print(f"HTTP error: {e.response.status_code}")
except httpx.RequestError as e:
    print(f"Request failed: {e}")
except Exception as e:
    print(f"Error: {e}")
```

### Rate Limiting
```python
import time
import httpx

def fetch_with_rate_limit(urls, delay=1.0):
    """Fetch URLs with rate limiting"""
    results = []
    for url in urls:
        response = httpx.get(url)
        results.append(response.json())
        time.sleep(delay)  # Wait between requests
    return results
```

### Pagination
```python
import httpx

def fetch_all_pages(base_url):
    """Fetch all pages from a paginated API"""
    all_data = []
    page = 1

    while True:
        response = httpx.get(f"{base_url}?page={page}")
        data = response.json()

        if not data.get("results"):
            break

        all_data.extend(data["results"])
        page += 1

        if not data.get("next"):
            break

    return all_data
```

## JSON Processing

### Parse and Extract
```python
import json

# Parse JSON string
data = json.loads(response.text)

# Access nested data
value = data["results"][0]["name"]

# Pretty print
print(json.dumps(data, indent=2))
```

### Filter and Transform
```python
# Filter items
filtered = [item for item in data if item["status"] == "active"]

# Transform structure
transformed = {
    item["id"]: {"name": item["name"], "value": item["value"]}
    for item in data
}

# Save to file
with open("output.json", "w") as f:
    json.dump(transformed, f, indent=2)
```

## Common Use Cases

### 1. Fetch Weather Data
```python
import httpx

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": "YOUR_API_KEY",
        "units": "metric"
    }

    response = httpx.get(url, params=params)
    data = response.json()

    return {
        "temperature": data["main"]["temp"],
        "description": data["weather"][0]["description"]
    }
```

### 2. Download and Save Images
```python
import httpx
from pathlib import Path

def download_image(url, filename):
    response = httpx.get(url)
    Path(filename).write_bytes(response.content)
    print(f"Downloaded: {filename}")
```

### 3. Monitor API Status
```python
import httpx
import time

def check_api_health(url, interval=60):
    """Check API health periodically"""
    while True:
        try:
            response = httpx.get(f"{url}/health", timeout=5.0)
            status = "UP" if response.status_code == 200 else "DOWN"
            print(f"API Status: {status}")
        except Exception as e:
            print(f"API Status: DOWN ({e})")

        time.sleep(interval)
```

## Tips

1. **Use appropriate timeouts**: Always set timeout values for HTTP requests
2. **Handle errors gracefully**: Catch and handle HTTP errors and network issues
3. **Respect rate limits**: Add delays between requests to avoid overwhelming servers
4. **Cache responses**: Store frequently accessed data locally
5. **Use async for concurrency**: Use async/await for parallel requests
6. **Validate data**: Check response status codes and validate JSON structure

## Environment Setup

Before using Python libraries, ensure they are installed:

```bash
# Create venv if not exists
if [ ! -d .venv ]; then uv venv; fi

# Install required packages
uv pip install httpx beautifulsoup4 lxml

# Run your script
uv run python your_script.py
```

## Reference

For more advanced usage and examples, see reference.md in this skill directory.
