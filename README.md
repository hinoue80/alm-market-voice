# ALM Market Voice

> Internal IBM market intelligence dashboard for the Asset Lifecycle Management (ALM) portfolio.
> Surfaces trending topics and demand signals from Reddit, analyst feeds, competitor websites, and public review sites — powering smarter sales plays and marketing campaigns for IBM Maximo and IBM Envizi.

---

## Quick Start (Local Development)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | [python.org](https://www.python.org) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| Docker Desktop | latest | [docker.com](https://www.docker.com) |
| PostgreSQL | via Docker | (included in docker-compose) |

---

### 1. Clone and configure environment

```bash
git clone https://github.ibm.com/YOUR-ORG/alm-market-voice.git
cd alm-market-voice

# Copy the example env file and fill in your keys
cp .env.example .env
```

Edit `.env` and fill in:

```
TAVILY_API_KEY=tvly-your-regenerated-key
WATSONX_API_KEY=your-ibm-cloud-api-key
WATSONX_PROJECT_ID=f76e0d92-2833-491f-b1a2-a5d5fbd0c2d0
```

---

### 2. Start the database

```bash
docker-compose up db -d
```

Wait a few seconds for PostgreSQL to be ready.

---

### 3. Start the backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the API server
uvicorn app.main:app --reload --port 8000
```

The backend will:
- Create all database tables on startup
- Seed the 20 default signal sources
- Start the weekly scheduler (runs every Monday 06:00 UTC)

API docs available at: **http://localhost:8000/api/docs**

---

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

### 5. Run your first ingestion

Once both servers are running, click **"⟳ Refresh Signals"** in the top-right of the dashboard, or call the API directly:

```bash
curl -X POST http://localhost:8000/api/ingest
```

The ingestion runs in the background. Check status at:

```bash
curl http://localhost:8000/api/ingest/status
```

---

## Running with Docker (recommended for sharing)

```bash
# Copy and fill in your .env first, then:
docker-compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/api/docs

---

## Architecture

```
alm-market-voice/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app entry point
│       ├── config.py            # Settings from .env
│       ├── models.py            # SQLAlchemy models + DB init + source seeding
│       ├── ingestion.py         # Pipeline orchestrator
│       ├── scheduler.py         # Weekly APScheduler job
│       ├── connectors/
│       │   ├── reddit.py        # Reddit JSON API + Tavily fallback
│       │   ├── rss_reader.py    # Analyst blog RSS feeds
│       │   └── web_crawler.py   # Tavily crawl/extract (competitors + reviews)
│       ├── enrichment/
│       │   └── watsonx.py       # IBM Granite topic/sentiment extraction
│       └── api/
│           └── routes.py        # REST endpoints
└── frontend/
    └── src/
        ├── App.jsx              # Root component + layout
        ├── api.js               # API client
        └── components/
            ├── SourceFilter.jsx # Sidebar source checkboxes
            ├── TopicChart.jsx   # Horizontal bar chart of trending topics
            ├── SignalFeed.jsx   # Paginated signal list with filters
            └── SummaryCards.jsx # Top-line KPI cards
```

---

## Signal Sources

### Reddit (via public JSON API)
- r/maximo
- r/facilitymanagement
- r/sustainability
- r/EAM
- r/assetmanagement

### Analyst RSS Feeds
- Gartner Blog
- IDC Blog
- Verdantix
- ARC Advisory Group

### Competitor Websites (crawled via Tavily)
- IFS
- MaintainX
- Hexagon (Asset Lifecycle Intelligence)
- Siemens (Asset Management)
- SAP (EAM)
- ServiceNow (IT Asset Management)

### Public Review Pages (extracted via Tavily)
- G2 — IBM Maximo
- G2 — IBM Envizi
- TrustRadius — IBM Maximo
- Gartner Peer Insights — IBM Maximo

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sources` | List all signal sources |
| PUT | `/api/sources/{id}/toggle` | Enable/disable a source |
| GET | `/api/signals` | Paginated signal feed (filterable) |
| GET | `/api/topics` | Trending topics by mention count |
| GET | `/api/topics/history` | Weekly trend for a specific topic |
| POST | `/api/ingest` | Trigger manual ingestion |
| GET | `/api/ingest/status` | Last ingestion run status |
| GET | `/health` | Health check |

### Signal feed query params

| Param | Type | Description |
|-------|------|-------------|
| `source_types` | string | Comma-separated: `reddit,rss,competitor,review` |
| `source_ids` | string | Comma-separated source IDs |
| `sentiment` | string | `positive`, `negative`, `neutral` |
| `signal_type` | string | `demand`, `complaint`, `competitive`, `analyst`, `general` |
| `topic` | string | Filter by topic substring |
| `days` | int | Look-back window (default: 30) |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Results per page (default: 20, max: 100) |

---

## IBM Cloud Deployment

For production deployment on IBM Cloud Code Engine:

1. Push code to `github.ibm.com`
2. Create an IBM Cloud PostgreSQL (Databases for PostgreSQL) instance
3. Build and push Docker images to IBM Container Registry
4. Deploy backend as a Code Engine application with your `.env` values as secrets
5. Deploy frontend as a static Code Engine application or serve it from the backend's `/dist` folder

See [IBM Cloud Code Engine docs](https://cloud.ibm.com/docs/codeengine) for step-by-step instructions.

---

## Adding New Sources

To add a new source, add a row to the `sources` table:

```python
# In models.py _seed_sources(), or directly via SQL:
INSERT INTO sources (name, source_type, url, enabled)
VALUES ('New Analyst Blog', 'rss', 'https://example.com/feed', 1);
```

Source types:
- `reddit` → uses `connectors/reddit.py`
- `rss` → uses `connectors/rss_reader.py`
- `competitor` → uses `connectors/web_crawler.py` (crawl)
- `review` → uses `connectors/web_crawler.py` (extract)

---

*Built for IBM ALM Product Marketing. Internal use only.*
