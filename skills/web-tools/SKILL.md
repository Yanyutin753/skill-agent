---
name: fetching-web-content
description: Provides expert guidance for HTTP requests, API interaction, and web scraping with Python. Use this skill when making API calls, fetching web pages, parsing HTML with BeautifulSoup, or processing JSON data.
allowed-tools: bash, read_file, write_file
---

# Fetching Web Content

## Overview

Tools for web operations: HTTP requests (curl/httpx), HTML parsing (BeautifulSoup), API interaction, JSON processing.

## Setup

```bash
uv pip install httpx beautifulsoup4 lxml
```

## HTTP Requests

### curl

```bash
curl https://api.example.com/data

curl -H "Authorization: Bearer TOKEN" https://api.example.com/protected

curl -X POST https://api.example.com/create \
     -H "Content-Type: application/json" \
     -d '{"name": "test"}'

curl -o output.json https://api.example.com/data
```

### httpx (Python)

```python
import httpx

response = httpx.get("https://api.example.com/data")
print(response.json())

response = httpx.post(
    "https://api.example.com/create",
    headers={"Authorization": "Bearer TOKEN"},
    json={"name": "test"}
)
```

### Async Requests

```python
import asyncio
import httpx

async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        return response.json()

data = asyncio.run(fetch_data())
```

## HTML Parsing

### BeautifulSoup Basics

```python
from bs4 import BeautifulSoup
import httpx

response = httpx.get("https://example.com")
soup = BeautifulSoup(response.text, "lxml")

title = soup.find("title").text
links = soup.find_all("a")
articles = soup.find_all("div", class_="article")
items = soup.select("div.container > p.text")
```

### Extract Table Data

```python
import csv

table = soup.find("table")
rows = [[col.text.strip() for col in row.find_all("td")] for row in table.find_all("tr")]

with open("data.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
```

## Error Handling

```python
import httpx

try:
    response = httpx.get("https://api.example.com/data", timeout=10.0)
    response.raise_for_status()
    data = response.json()
except httpx.HTTPStatusError as e:
    print(f"HTTP error: {e.response.status_code}")
except httpx.RequestError as e:
    print(f"Request failed: {e}")
```

## Rate Limiting

```python
import time
import httpx

def fetch_with_delay(urls, delay=1.0):
    results = []
    for url in urls:
        results.append(httpx.get(url).json())
        time.sleep(delay)
    return results
```

## Pagination

```python
def fetch_all_pages(base_url):
    all_data, page = [], 1
    while True:
        data = httpx.get(f"{base_url}?page={page}").json()
        if not data.get("results"):
            break
        all_data.extend(data["results"])
        if not data.get("next"):
            break
        page += 1
    return all_data
```

## JSON Processing

```python
import json

data = json.loads(response.text)
filtered = [item for item in data if item["status"] == "active"]
transformed = {item["id"]: item["name"] for item in data}

with open("output.json", "w") as f:
    json.dump(transformed, f, indent=2)
```

## Common Patterns

### Download File

```python
from pathlib import Path
import httpx

def download(url, filename):
    Path(filename).write_bytes(httpx.get(url).content)
```

### API Health Check

```python
def check_health(url):
    try:
        r = httpx.get(f"{url}/health", timeout=5.0)
        return r.status_code == 200
    except:
        return False
```

## Guidelines

1. Always set timeout values
2. Handle HTTP errors and network issues
3. Respect rate limits with delays
4. Cache frequently accessed data
5. Use async for concurrent requests
6. Validate response status codes
