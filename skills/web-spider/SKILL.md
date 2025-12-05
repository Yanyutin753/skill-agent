---
name: web-spider
description: Web scraping and crawling using Firecrawl - transform websites into LLM-ready markdown and structured data
license: MIT
allowed-tools: ["bash_tool", "read_file", "write_file"]
---

# Web Spider Skill (Firecrawl)

Firecrawl is an API service that crawls websites and extracts clean markdown or structured data, optimized for LLM consumption.

## Installation

```bash
pip install firecrawl-py
```

## Authentication

```python
from firecrawl import Firecrawl

app = Firecrawl(api_key="fc-YOUR_API_KEY")
```

## Core Features

### 1. Scrape - Single URL

```python
from firecrawl import Firecrawl

app = Firecrawl(api_key="fc-YOUR_API_KEY")

result = app.scrape(
    'https://example.com',
    formats=['markdown', 'html', 'links', 'screenshot'],
    timeout=30000,
    wait_for=2000
)

print(result.markdown)
print(f"Found {len(result.links)} links")
```

### 2. Crawl - Entire Website

```python
from firecrawl.types import ScrapeOptions

crawl_result = app.crawl(
    'https://docs.example.com',
    limit=100,
    max_depth=3,
    scrape_options=ScrapeOptions(formats=['markdown', 'html']),
    exclude_paths=['blog/*', 'admin/*'],
    include_paths=['docs/**'],
    poll_interval=5
)

print(f"Crawled {len(crawl_result.data)} pages")
print(f"Credits used: {crawl_result.credits_used}")
```

### 3. Map - Discover All URLs

```python
map_result = app.map(
    'https://example.com',
    search='documentation',
    ignore_sitemap=False,
    include_subdomains=False,
    limit=100
)

print(f"Found {len(map_result.links)} URLs")
for link in map_result.links[:5]:
    print(f"{link.title}: {link.url}")
```

### 4. Search - Web Search with Content

```python
search_result = app.search(
    'what is web scraping?',
    limit=5,
    lang='en',
    country='us',
    scrape_options=ScrapeOptions(formats=['markdown'])
)

for result in search_result.data:
    print(f"{result.title}: {result.url}")
    print(f"Content: {result.markdown[:200]}...")
```

### 5. Extract - Structured Data with AI

```python
from pydantic import BaseModel, Field
from typing import List

class Article(BaseModel):
    title: str
    points: int
    by: str
    url: str

class TopArticles(BaseModel):
    articles: List[Article] = Field(..., description="Top 5 stories")

extract_result = app.extract(
    urls=['https://news.ycombinator.com'],
    schema=TopArticles,
    prompt='Extract the top 5 stories from Hacker News'
)

for article in extract_result.data.articles:
    print(f"{article.title} by {article.by} ({article.points} points)")
```

### 6. Actions - Interact with Pages

```python
actions = [
    {"type": "wait", "milliseconds": 2000},
    {"type": "click", "selector": "#search-button"},
    {"type": "write", "text": "firecrawl", "selector": "#search-input"},
    {"type": "press", "key": "Enter"},
    {"type": "wait", "milliseconds": 3000},
    {"type": "screenshot"}
]

result = app.scrape(
    'https://example.com',
    formats=['markdown', 'screenshot'],
    actions=actions
)
```

## Advanced Usage

### Batch Scrape Multiple URLs

```python
batch_result = app.batch_scrape(
    urls=[
        'https://example1.com',
        'https://example2.com',
        'https://example3.com'
    ],
    formats=['markdown', 'html'],
    poll_interval=3
)

print(f"Scraped {len(batch_result.data)} URLs")
```

### LLM Extraction in Scrape

```python
result = app.scrape(
    'https://firecrawl.dev',
    formats=[
        'markdown',
        {
            'type': 'json',
            'prompt': 'Extract company mission, key features, and pricing'
        }
    ]
)

print(result.json)
```

### Real-time Crawl with WebSocket

```python
import asyncio

def on_document(detail):
    print(f"Scraped: {detail['metadata']['sourceURL']}")

def on_done(detail):
    print(f"Crawl completed: {detail['status']}")

async def realtime_crawl():
    watcher = app.crawl_url_and_watch(
        'https://example.com',
        exclude_paths=['blog/*'],
        limit=20
    )
    watcher.add_event_listener("document", on_document)
    watcher.add_event_listener("done", on_done)
    await watcher.connect()

asyncio.run(realtime_crawl())
```

### Async Crawl with Status Polling

```python
crawl_job = app.start_crawl(
    'https://example.com',
    limit=50,
    exclude_paths=['blog/*']
)
print(f"Job ID: {crawl_job.id}")

status = app.get_crawl_status(crawl_job.id)
print(f"Status: {status.status}")
print(f"Progress: {status.completed}/{status.total}")

if status.status == 'scraping':
    app.cancel_crawl(crawl_job.id)
```

## Output Formats

| Format | Description |
|--------|-------------|
| `markdown` | Clean markdown content |
| `html` | Raw HTML |
| `links` | All links on the page |
| `screenshot` | Page screenshot |
| `json` | Structured data extraction |
| `attributes` | Specific element attributes |

## Scrape Options

```python
from firecrawl.types import ScrapeOptions

options = ScrapeOptions(
    formats=['markdown', 'html'],
    only_main_content=True,
    include_tags=['article', 'main'],
    exclude_tags=['nav', 'footer'],
    wait_for=2000,
    timeout=30000
)
```

## Best Practices

1. **Use appropriate limits**: Set `limit` and `max_depth` to avoid over-crawling
2. **Filter paths**: Use `include_paths` and `exclude_paths` for targeted crawling
3. **Handle rate limits**: Use `poll_interval` to control request frequency
4. **Extract structured data**: Use Pydantic schemas for type-safe extraction
5. **Monitor credits**: Check `credits_used` in responses

## Alternative: Basic HTTP Requests

For simple requests without Firecrawl:

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

## Reference

- Firecrawl Docs: https://docs.firecrawl.dev
- Python SDK: https://github.com/mendableai/firecrawl
