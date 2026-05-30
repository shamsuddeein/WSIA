# WSIA — Web Security Intelligence Architecture

A security intelligence pipeline that scrapes, cleans, stores, and serves web3/DeFi vulnerability data via a REST API. Built with Django, Celery, and an optional OpenAI layer.

---

## Table of Contents

- [Overview](#overview)
- [System Flow](#system-flow)
- [Tech Stack](#tech-stack)
- [Data Schema](#data-schema)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Build Phases](#build-phases)
- [Design Rules](#design-rules)

---

## Overview

WSIA aggregates security incident reports from sources like [rekt.news](https://rekt.news), normalises the data, assigns categories and severity, and serves it through a filterable REST API. An AI layer (GPT-4o-mini) adds plain-English summaries and embedding-based similarity matching as an optional, non-critical feature.

**Core principle:** data integrity before features. The pipeline must be correct before it is smart.

---

## System Flow

```
Scraper (rekt.news)
      │
      ▼
  Raw Storage          ← HackReport, is_processed=False
      │
      ▼
  Analytics            ← clean text, assign category & severity
      │
      ▼
  Reports DB           ← structured, deduplicated, indexed
      │
      ▼
  REST API             ← paginated list, detail, filters
      │
      ▼
  Search               ← keyword, category, severity, date
      │
      ▼
  AI Layer (optional)  ← summaries, similarity, pattern tags
```

Each stage depends on the one above it being stable. Don't skip ahead.

---

## Tech Stack

| Package | Version | Purpose |
|---|---|---|
| Python | 3.11 / 3.12 | Runtime |
| Django | 4.2 LTS | Core framework |
| djangorestframework | 3.15 | REST API |
| django-filter | 23.5 | Query param filtering |
| psycopg2-binary | 2.9 | PostgreSQL adapter |
| requests | 2.31 | HTTP client for scraper |
| beautifulsoup4 | 4.12 | HTML parsing |
| lxml | 4.9 | Fast BS4 parser backend |
| python-dotenv | 1.0 | Load `.env` secrets |
| celery | 5.3 | Task queue (Phase 5+) |
| redis | 5.0 | Celery broker (Phase 5+) |
| openai | 1.x | AI integration (Phase 7 only) |

> **Note:** Do not install `openai` until you reach Phase 7.

---

## Data Schema

### Category

| Field | Type | Notes |
|---|---|---|
| id | AutoField | Primary key |
| name | CharField(100) | e.g. Reentrancy, Flash Loan |
| slug | SlugField | Auto-generated from name — must be unique |
| created_at | DateTimeField | auto_now_add=True |

### Tag

| Field | Type | Notes |
|---|---|---|
| id | AutoField | Primary key |
| name | CharField(50) | Short label, e.g. `defi`, `bridge` |
| created_at | DateTimeField | auto_now_add=True |

### HackReport

| Field | Type | Notes |
|---|---|---|
| id | AutoField | Primary key |
| title | CharField(300) | Report headline |
| description | TextField | Raw or cleaned body text |
| source_url | URLField | Original article URL |
| source | CharField(50) | Provider name, e.g. `rekt.news` |
| severity | CharField(20) | Choices: `low / medium / high / critical` |
| category | ForeignKey(Category) | on_delete=SET_NULL, null=True |
| tags | ManyToManyField(Tag) | blank=True |
| is_processed | BooleanField | False until Analytics cleans it |
| created_at | DateTimeField | auto_now_add=True |
| published_at | DateTimeField | null=True — original publication date |
| hash | CharField(64) | SHA-256 of source_url — unique=True, db_index=True |
| raw_data | JSONField | default=dict — source-specific metadata |
| ai_summary | TextField | null=True — added in Phase 7 migration |

**Relationships:**
```
Category  (1) ──< HackReport (many)
Tag       (many) >──< HackReport (many)   [ManyToMany]
```

**Deduplication:** `hash` is the dedup key. A SHA-256 of `source_url` is computed before every insert. `unique=True` at the database level protects against race conditions during automated scraping.

---

## Project Structure

```
wsia/
├── core/
│   ├── models.py
│   └── ...
├── reports/
│   ├── models.py           ← Category, Tag, HackReport
│   ├── admin.py
│   ├── migrations/
│   └── services/
│       ├── __init__.py
│       ├── report_service.py     ← create/update report logic
│       ├── dedup_service.py      ← hash computation and duplicate check
│       └── category_service.py  ← keyword-based category assignment
├── api/
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── analytics/
│   └── ...                 ← text cleaning and normalisation (Phase 4)
├── manage.py
├── requirements.txt
└── .env                    ← never commit this
```

---

## Getting Started

### Prerequisites

- Python 3.11 or 3.12
- PostgreSQL 14+
- Redis (required from Phase 5 onwards)

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd wsia

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your database credentials and secret key

# 5. Run migrations
python manage.py migrate

# 6. Create a superuser
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Visit `http://localhost:8000/admin/` to access Django Admin.

### Running Celery (Phase 5+)

```bash
# Start Redis
redis-server

# Start Celery worker
celery -A wsia worker --loglevel=info

# Start Celery beat scheduler
celery -A wsia beat --loglevel=info
```

---

## Environment Variables

Create a `.env` file in the project root. **Never commit this file to Git.**

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
DATABASE_URL=postgres://user:password@localhost:5432/wsia
OPENAI_API_KEY=sk-...    # Phase 7 only — add when needed
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/reports/` | Paginated list of all processed reports |
| GET | `/api/reports/{id}/` | Single report by ID |
| GET | `/api/reports/?category=defi` | Filter by category slug |
| GET | `/api/reports/?severity=high` | Filter by severity |
| GET | `/api/search/?q=reentrancy` | Full-text search across title and description |
| GET | `/api/search/?category=&severity=&date_from=` | Combined filters |

**Pagination:** 20 results per page (configurable via `PAGE_SIZE` in DRF settings).

---

## Build Phases

| Phase | Name | Status |
|---|---|---|
| 0 | Project Foundation | Django scaffold, Git, PostgreSQL config |
| 1 | Database Core | Models, migrations, services/ layer, admin |
| 2 | Basic API | DRF serializers, viewsets, filters, pagination |
| 3 | First Scraper | rekt.news scraper with rate limiting and dedup |
| 4 | Data Cleaning | Text normalisation, category and severity assignment |
| 5 | Pipeline Automation | Celery + Redis periodic task, end-to-end pipeline |
| 6 | Search & Filtering | `/api/search/` with Q() queries and combined filters |
| 7 | AI Integration | GPT-4o-mini summaries, embedding-based similarity |

**Start here:** Complete Phase 0 and Phase 1 first. Stop when you can create a `HackReport` through Django Admin and read it back from the database. Do not touch Celery, Redis, Search, AI, or a second scraper until Phase 1 passes all its checks.

---

## Design Rules

**Do:**
- Build the database first, always
- Test each phase independently before moving on
- Back up the database before running new migrations: `pg_dump wsia > backup_$(date +%Y%m%d).sql`
- Keep the system runnable without the AI layer
- Check for existing records by hash before inserting
- Keep models thin — business logic belongs in `services/`

**Don't:**
- Build the AI layer before the data pipeline exists
- Scrape multiple sites during early phases
- Mix scraper logic with API code
- Optimise or refactor before Phase 5
- Commit secrets or `.env` files to Git

---

## Architecture Rating

**8.5 / 10** — Strong phased discipline, one-source-first principle, AI as a late optional layer. The foundation is sound; the remaining headroom is around long-term maintainability and horizontal scaling.

---

## Appendices

| | Topic |
|---|---|
| A | Database Design — production-level Django models with all fields, choices, and relationships |
| B | Phase 0 & 1 Setup — step-by-step commands for the Django project and first models |
| C | First Scraper (rekt.news) — structured scraper design with rate limiting and error handling |
