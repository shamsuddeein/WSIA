# API Documentation

This document describes the REST API exposed by the Django backend in `/api/`.

Base URL
--------

- Local/dev base path: `/api/`

Authentication
--------------

- The current implementation does not document explicit authentication requirements.
- If your deployment uses authentication or API tokens, protect these endpoints accordingly.

Common query parameters
-----------------------

- `page`: integer page number for paginated endpoints.
- `ordering`: field to sort by. Prefix with `-` for descending order.

Supported ordering fields:
- `published_at`
- `created_at`
- `severity`
- `title`

Report list and search filtering
--------------------------------

The list and search endpoints support these filters:
- `q`: full-text search query for title, description, and tags.
- `category`: category slug.
- `severity`: severity level.
- `source`: report source.
- `is_processed`: boolean status (`true` or `false`).
- `tag`: tag name.
- `published_after`: ISO 8601 date/time filter.
- `published_before`: ISO 8601 date/time filter.
- `created_after`: ISO 8601 date/time filter.
- `created_before`: ISO 8601 date/time filter.

### Severity values

- `low`
- `medium`
- `high`
- `critical`

Developer guide
---------------

This section is designed for backend and frontend engineers integrating with the `/api/` service.

### Core concepts

- `/api/reports/` is the primary list endpoint for HackReport records.
- `/api/search/` is optimized for keyword lookup across titles and descriptions.
- `/api/reports/{id}/similar/` returns related reports using vector embeddings.
- `/api/stats/` is useful for dashboards or health checks showing dataset coverage.
- `/api/categories/` returns categories with report counts.

### Recommended usage patterns

1. Use `/api/reports/` for pagination, filtering, and browsing by category/severity.
2. Use `/api/search/` when the user enters a free-text query.
3. Use `/api/reports/{id}/similar/` to recommend related reports after a detail view.
4. Use `/api/stats/` for metrics and monitoring.

### Example cURL flows

List high-severity DeFi reports:

```bash
curl "http://localhost:8000/api/reports/?severity=high&category=defi&ordering=-published_at"
```

Search for reports containing “reentrancy”:

```bash
curl "http://localhost:8000/api/search/?q=reentrancy&severity=high"
```

Fetch a report detail:

```bash
curl "http://localhost:8000/api/reports/42/"
```

Get similar reports for report 42:

```bash
curl "http://localhost:8000/api/reports/42/similar/?k=5"
```

### Example Python client

```python
import requests

BASE = "http://localhost:8000/api"

# List reports
r = requests.get(f"{BASE}/reports/", params={
    "category": "defi",
    "severity": "high",
    "ordering": "-published_at",
})
reports = r.json()["results"]

# Search
r = requests.get(f"{BASE}/search/", params={"q": "reentrancy"})
search_results = r.json()["results"]

# Report detail
r = requests.get(f"{BASE}/reports/42/")
report = r.json()

# Similar reports
r = requests.get(f"{BASE}/reports/42/similar/", params={"k": 5})
similar_reports = r.json()
```

### Response structure notes

- List endpoints use `HackReportListSerializer`, so list items include `category_name`, `category_slug`, and `tag_names`.
- Detail endpoints use `HackReportSerializer`, which includes nested `category` and `tags` objects.
- Search results also include an `excerpt` field for the matched report description.

Endpoints
---------

### GET /api/reports/

Returns a paginated list of hack reports.

Query parameters:
- `page`
- `ordering`
- `q`
- `category`
- `severity`
- `source`
- `is_processed`
- `tag`
- `published_after`
- `published_before`
- `created_after`
- `created_before`

Response shape:
- `count`: total number of matching reports.
- `next`: URL of next page.
- `previous`: URL of previous page.
- `results`: array of report objects.

Each report object includes:
- `id`
- `title`
- `source`
- `source_url`
- `severity`
- `severity_display`
- `category_name`
- `category_slug`
- `tag_names`
- `is_processed`
- `published_at`
- `created_at`

Example request:

```bash
curl "http://localhost:8000/api/reports/?severity=high&category=defi&ordering=-published_at"
```

### GET /api/reports/{id}/

Returns a single report by numeric ID.

Response fields:
- `id`
- `title`
- `description`
- `source_url`
- `source`
- `severity`
- `severity_display`
- `category`
- `tags`
- `is_processed`
- `ai_summary`
- `published_at`
- `created_at`

### GET /api/reports/{id}/similar/

Returns reports similar to the specified report using vector embeddings.

Query parameters:
- `k` (optional): number of similar reports to return. Default: 5.

Response shape:
- `id`
- `title`
- `source`
- `source_url`
- `severity`
- `severity_display`
- `category_name`
- `category_slug`
- `tag_names`
- `is_processed`
- `published_at`
- `created_at`

Example request:

```bash
curl "http://localhost:8000/api/reports/123/similar/?k=5"
```

### GET /api/search/

Performs a text search across reports and returns matching results.

Required query parameter:
- `q`: search query string.

Optional filter query parameters:
- `category`
- `severity`
- `source`
- `is_processed`
- `tag`
- `published_after`
- `published_before`
- `created_after`
- `created_before`
- `ordering`

Response shape:
- `count`
- `next`
- `previous`
- `results`

Each result object includes:
- `id`
- `title`
- `source`
- `source_url`
- `severity`
- `severity_display`
- `category_name`
- `category_slug`
- `tag_names`
- `is_processed`
- `published_at`
- `created_at`
- `excerpt`

Example request:

```bash
curl "http://localhost:8000/api/search/?q=reentrancy&severity=high"
```

### GET /api/stats/

Returns aggregated statistics for reports.

Response object:
- `total_reports`
- `processed_reports`
- `unprocessed_reports`
- `by_severity`
- `by_source`
- `top_categories`

Example response:

```json
{
  "total_reports": 1284,
  "processed_reports": 1120,
  "unprocessed_reports": 164,
  "by_severity": {
    "low": 430,
    "medium": 500,
    "high": 260,
    "critical": 94
  },
  "by_source": {
    "onchain": 800,
    "offchain": 484
  },
  "top_categories": [
    {"name": "DeFi", "slug": "defi", "count": 420},
    {"name": "NFT", "slug": "nft", "count": 210}
  ]
}
```

### GET /api/categories/

Returns category metadata and counts.

Response shape:
- `count`
- `next`
- `previous`
- `results`

Each category object includes:
- `id`
- `name`
- `slug`
- `report_count`

Example request:

```bash
curl "http://localhost:8000/api/categories/"
```

### GET /api/health/

Returns a simple health check response.

Example response:

```json
{
  "status": "ok"
}
```

Implementation notes
--------------------

- `/api/reports/` and `/api/search/` are backed by DRF viewsets and filter sets.
- The `/api/reports/{id}/similar/` endpoint relies on stored vector embeddings and cosine similarity.
- The `is_processed` field indicates whether the report has been fully ingested and enriched by the background pipeline.
- `ai_summary` is an optional field populated when report enrichment has produced an AI-generated summary.
- If your environment uses Postgres with `pgvector`, the similarity search endpoint will use that vector store.

Change log
----------

- Created API reference for the current backend implementation.
