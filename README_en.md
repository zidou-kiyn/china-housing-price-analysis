# Urban Housing Price Analysis System

> A machine-learning-powered platform for collecting, visualizing, and forecasting housing prices across 330+ cities in China.

[中文](./README.md)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-AA344D?style=flat-square&logo=apacheecharts&logoColor=white)](https://echarts.apache.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

## Screenshots

<p align="center">
  <img src="docs/images/首页大屏.png" width="90%" alt="Home Dashboard" />
</p>

| Heat Map | Price Forecast | Admin Panel |
|:---:|:---:|:---:|
| ![Heat Map](docs/images/热力地图.png) | ![Price Forecast](docs/images/预测页面.png) | ![Admin Panel](docs/images/管理后台.png) |

## Features

### Data Collection

- Pluggable source adapter architecture, currently integrated with creprice.cn
- Monthly housing price data for 330+ cities and their districts
- Anti-scraping: UA rotation, random delays, exponential backoff retries
- Proxy support (HTTP/HTTPS/SOCKS5) with admin-configurable connectivity testing
- Pipeline validation: price range clamping (500–200,000 CNY/m²) and 40% MoM jump detection

### Data Visualization

- City & district price trend lines with multi-source overlay
- GeoJSON-based choropleth heat maps (333 city vector boundaries)
- Multi-region comparison charts (2–5 cities/districts side by side)
- Price ranking tables with supply/attention/average price sorting, MoM & YoY changes
- Price range distribution pie charts
- Comprehensive dashboard combining trends, heat maps, distributions, and rankings

### ML Forecasting

- Three algorithms: Random Forest, XGBoost, Exponential Smoothing (Holt-Winters)
- Rolling multi-step forecasts up to 12 months ahead
- Confidence interval estimation (inter-tree variance for RF, residual-based for XGBoost/ES)
- 15+ engineered features: lags, rolling statistics, MoM/YoY, seasonality, city tier
- Model version management with active pointer, cleanup policy, and best-MAPE tracking
- Data quality annotation (monthly observed / annual interpolation / mixed)

### Authentication & Authorization

- JWT-based auth (registration, login, auto-redirect on token expiry)
- Role-based access control (user / admin)
- Admin management of user accounts and roles

### Admin Platform

- Data management: city coverage tree, batch collection triggers, job progress polling
- Model management: training triggers, version listing, activation switching, bulk cleanup
- User management: search, role changes, enable/disable, delete
- System settings: crawler proxy configuration and connectivity testing

### Infrastructure

- Docker Compose one-command deployment (dev / prod dual-mode)
- Redis caching layer (30–60 min TTL, auto-invalidation on data updates)
- Alembic database migrations (8 versions, full migration chain)
- 35 backend test files covering API, collector, ML, pipeline, and service layers

## Architecture

```mermaid
graph TB
    subgraph Client
        Browser["Browser"]
    end

    subgraph Frontend Container
        Nginx["Nginx / Vite Dev Server"]
        Vue["Vue 3 + Element Plus + ECharts"]
    end

    subgraph Backend Container
        API["FastAPI REST API"]
        Services["Service Layer"]
        Collector["Data Collection Pipeline"]
        ML["ML Pipeline<br/>RF · XGBoost · ExpSmoothing"]
    end

    subgraph Data Layer
        PG[("PostgreSQL 16")]
        RD[("Redis 7")]
    end

    subgraph External Source
        Source["creprice.cn"]
    end

    Browser --> Nginx
    Nginx --> Vue
    Vue -->|"/api/*"| API
    API --> Services
    Services --> ML
    Services --> Collector
    Services --> PG
    Services --> RD
    Collector -->|"HTTP Crawl"| Source
    ML -->|"Training Data"| PG
    ML -->|".pkl Models"| Models["models/"]
```

## Tech Stack

### Backend

| Category | Technologies |
|----------|-------------|
| Web Framework | FastAPI 0.111+ · Uvicorn · Pydantic v2 |
| Database | PostgreSQL 16 · SQLAlchemy 2.0 (async) · Alembic |
| Cache | Redis 7 |
| Authentication | python-jose (JWT) · bcrypt |
| Machine Learning | scikit-learn · XGBoost · statsmodels · pandas · NumPy |
| Data Collection | httpx · requests · BeautifulSoup4 · lxml |

### Frontend

| Category | Technologies |
|----------|-------------|
| Framework | Vue 3.4 (Composition API + `<script setup>`) · TypeScript 5.5 |
| Build Tool | Vite 5.3 |
| UI Components | Element Plus 2.7 |
| Charts | ECharts 5.5 (with GeoJSON maps) |
| State Management | Pinia 2.1 |
| HTTP Client | Axios 1.7 |

### Infrastructure

| Category | Technologies |
|----------|-------------|
| Containerization | Docker · Docker Compose (dev overlay + prod baseline) |
| Reverse Proxy | Nginx 1.27 (production) · Vite Proxy (development) |
| Testing | pytest · pytest-asyncio · Playwright |
| Code Quality | Ruff · mypy · vue-tsc |

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) v2+
- Git

### Launch

```bash
# 1. Clone the repository
git clone https://github.com/zidou-kiyn/china-housing-price-analysis.git
cd china-housing-price-analysis

# 2. Start all services (dev mode, auto-merges docker-compose.override.yml)
docker compose up -d --build

# 3. Wait for services to be ready (first run auto-migrates DB and seeds city data)
docker compose logs -f backend
# Press Ctrl+C once you see "Uvicorn running on http://0.0.0.0:8000"

# 4. Create an admin account
docker compose exec backend uv run --no-sync python scripts/create_admin.py admin admin@example.com your_password

# 5. Open the app
# Frontend: http://localhost:5173
# API docs: http://localhost:5173/api/docs (proxied through Vite)
```

### Environment Variables

Dev mode reads from the `.env` file at the project root:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async connection string | `postgresql+asyncpg://postgres:postgres@postgres:5432/housing_price` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | JWT signing key | `dev-only-insecure-key` (must change in production) |
| `CRAWL_CONCURRENCY` | Crawler concurrency | `3` |

For production, copy `.env.prod`, replace sensitive values, and run:

```bash
docker compose -f docker-compose.yml --env-file .env.prod up -d --build
```

<details>
<summary><strong>Manual Deployment (without Docker)</strong></summary>

#### Prerequisites

- Python 3.11+ (recommend [uv](https://docs.astral.sh/uv/) for dependency management)
- Node.js 20+
- PostgreSQL 16
- Redis 7

#### Backend

```bash
cd backend

# Install dependencies
uv sync

# Configure environment variables (edit DATABASE_URL etc. to point to local DB)
cp ../.env .env
# Edit .env: change postgres/redis hostnames from container names to localhost

# Run database migrations
uv run alembic upgrade head

# Create admin account
uv run python scripts/create_admin.py admin admin@example.com your_password

# Start backend (dev mode with hot reload)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm ci

# Start dev server (auto-proxies /api to localhost:8000)
npm run dev
```

Open `http://localhost:5173` in your browser.

</details>

## Project Structure

```
Urban-Housing-Price-Analysis-System/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST API routes (auth, cities, prices, analytics, predictions, admin_*)
│   │   ├── collector/       # Data collectors (source adapters, HTTP client, storage)
│   │   ├── core/            # Config, security, source policy
│   │   ├── ml/              # Machine learning (training, prediction, feature engineering, dataset builder)
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── pipeline/        # Collection pipeline (cleaning, validation, upsert)
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   └── services/        # Business logic layer
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Ops scripts (create admin, fetch GeoJSON, etc.)
│   ├── seed/                # City seed data
│   └── tests/               # Backend tests
├── frontend/
│   └── src/
│       ├── api/             # Axios API modules
│       ├── components/      # Vue components (charts, maps, selectors)
│       ├── composables/     # Composition functions
│       ├── stores/          # Pinia state management
│       ├── views/           # Page views (11 pages)
│       └── router/          # Route configuration
├── data/                    # Persistent data (GeoJSON, raw crawl data, DB files)
├── docker-compose.yml       # Production baseline config
├── docker-compose.override.yml  # Dev mode overlay config
└── .env                     # Dev environment variables
```

## License

This project is licensed under the [MIT License](./LICENSE).
