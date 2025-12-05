---
name: scraping-websites
description: Provides expert guidance for web scraping and crawling using Firecrawl API. Use this skill when extracting content from websites, crawling documentation sites, converting web pages to markdown, or extracting structured data from HTML.
allowed-tools: bash, read_file, write_file
---

# Scraping Websites with Firecrawl

## Overview

Firecrawl transforms websites into LLM-ready markdown and structured data. Core capabilities:
- **Scrape**: Extract single page content
- **Crawl**: Recursively process entire sites
- **Map**: Discover all URLs on a domain
- **Search**: Web search with content extraction
- **Extract**: AI-powered structured data extraction

## Setup

```bash
pip install firecrawl-py
```

```python
from firecrawl import Firecrawl
app = Firecrawl(api_key="fc-YOUR_API_KEY")
```

## Core Methods

### Scrape Single Page
```python
result = app.scrape(
    'https://example.com',
    formats=['markdown', 'html', 'links'],
    timeout=30000,
    wait_for=2000
)
print(result.markdown)
```

### Crawl Entire Site
```python
from firecrawl.types import ScrapeOptions

crawl_result = app.crawl(
    'https://docs.example.com',
    limit=100,
    max_depth=3,
    scrape_options=ScrapeOptions(formats=['markdown']),
    exclude_paths=['blog/*'],
    include_paths=['docs/**']
)
```

### Map URLs
```python
map_result = app.map('https://example.com', search='api', limit=100)
for link in map_result.links:
    print(f"{link.title}: {link.url}")
```

### Search Web
```python
search_result = app.search('python async tutorial', limit=5, lang='en')
for r in search_result.data:
    print(f"{r.title}: {r.markdown[:200]}")
```

### Extract Structured Data
```python
from pydantic import BaseModel
from typing import List

class Product(BaseModel):
    name: str
    price: float
    description: str

class Products(BaseModel):
    items: List[Product]

result = app.extract(
    urls=['https://shop.example.com'],
    schema=Products,
    prompt='Extract all products with prices'
)
```

## Page Actions

Interact with pages before scraping:
```python
actions = [
    {"type": "wait", "milliseconds": 2000},
    {"type": "click", "selector": "#load-more"},
    {"type": "write", "text": "query", "selector": "#search"},
    {"type": "press", "key": "Enter"},
    {"type": "screenshot"}
]
result = app.scrape('https://example.com', actions=actions)
```

## Output Formats

| Format | Description |
|--------|-------------|
| `markdown` | Clean markdown |
| `html` | Raw HTML |
| `links` | Page links |
| `screenshot` | Page image |
| `json` | Structured extraction |

## Scrape Options
```python
from firecrawl.types import ScrapeOptions

options = ScrapeOptions(
    formats=['markdown'],
    only_main_content=True,
    include_tags=['article', 'main'],
    exclude_tags=['nav', 'footer'],
    wait_for=2000,
    timeout=30000
)
```

## Batch Operations
```python
batch_result = app.batch_scrape(
    urls=['https://a.com', 'https://b.com', 'https://c.com'],
    formats=['markdown'],
    poll_interval=3
)
```

## Async Crawl
```python
job = app.start_crawl('https://example.com', limit=50)
status = app.get_crawl_status(job.id)
print(f"Progress: {status.completed}/{status.total}")
```

## Guidelines

1. Set `limit` and `max_depth` to avoid over-crawling
2. Use `include_paths`/`exclude_paths` for targeted crawling
3. Use `poll_interval` to respect rate limits
4. Use Pydantic schemas for type-safe extraction
5. Monitor `credits_used` in responses

## Reference

- Docs: https://docs.firecrawl.dev
- SDK: https://github.com/mendableai/firecrawl
