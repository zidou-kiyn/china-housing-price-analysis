# 城市房价分析系统

> 基于机器学习的中国城市房价数据采集、可视化分析与趋势预测系统，覆盖全国 330+ 城市

[English](./README_en.md)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vue](https://img.shields.io/badge/Vue-3.4-4FC08D?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![ECharts](https://img.shields.io/badge/ECharts-5.5-AA344D?style=flat-square&logo=apacheecharts&logoColor=white)](https://echarts.apache.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

## 截图预览

<p align="center">
  <img src="docs/image/首页大屏.png" width="90%" alt="首页大屏" />
</p>

| 热力地图 | 趋势预测 | 管理后台 |
|:---:|:---:|:---:|
| ![热力地图](docs/image/热力地图.png) | ![趋势预测](docs/image/预测页面.png) | ![管理后台](docs/image/管理后台.png) |

## 功能特性

### 数据采集

- 可插拔数据源适配器架构，当前接入 creprice.cn
- 覆盖全国 330+ 城市及下辖区县的月度房价数据
- UA 轮换、随机延迟、指数退避重试等反爬策略
- 支持 HTTP/HTTPS/SOCKS5 代理配置与连通性测试
- 采集管道内置价格区间校验（500–200,000 元/㎡）与环比跳变检测（40% 阈值）

### 数据可视化

- 城市/区县房价趋势折线图（多源叠加展示）
- 基于 GeoJSON 的城市热力地图（333 城市矢量边界）
- 多区域对比图（支持 2–5 个城市/区县同时对比）
- 房价排行榜（供应价/关注价/均价排序，含环比/同比变化）
- 价格区间分布饼图
- 综合数据大屏（趋势 + 热力图 + 分布 + 排行一屏展示）

### 机器学习预测

- 三种算法：Random Forest、XGBoost、Exponential Smoothing (Holt-Winters)
- 滚动多步预测，支持 1–12 个月前瞻
- 置信区间估计（RF 基于树间方差，XGBoost/ES 基于残差）
- 15+ 特征工程：滞后特征、滚动统计、环比/同比、季节性、城市等级
- 模型版本管理（版本号、激活指针、清理策略、最优 MAPE 追踪）
- 数据质量标注（月度实采 / 年度插值 / 混合）

### 用户与权限

- JWT 认证（注册、登录、Token 自动续期）
- 角色权限控制（普通用户 / 管理员）
- 管理员可管理用户账号状态与角色

### 管理后台

- 数据管理：城市覆盖状态树、批量采集任务触发、任务进度轮询
- 模型管理：训练触发、版本列表、激活切换、批量清理
- 用户管理：搜索、角色变更、启用/禁用、删除
- 系统设置：爬虫代理配置与连通性测试

### 基础设施

- Docker Compose 一键部署（dev / prod 双模式）
- Redis 缓存层（30–60 分钟 TTL，数据更新后自动失效）
- Alembic 数据库迁移（8 个版本，完整迁移链）
- 35 个后端测试文件，覆盖 API / 采集器 / ML / 管道 / 服务层

## 系统架构

```mermaid
graph TB
    subgraph 客户端
        Browser["浏览器"]
    end

    subgraph 前端容器
        Nginx["Nginx / Vite Dev Server"]
        Vue["Vue 3 + Element Plus + ECharts"]
    end

    subgraph 后端容器
        API["FastAPI REST API"]
        Services["业务服务层"]
        Collector["数据采集管线"]
        ML["ML 管线<br/>RF · XGBoost · ExpSmoothing"]
    end

    subgraph 数据层
        PG[("PostgreSQL 16")]
        RD[("Redis 7")]
    end

    subgraph 外部数据源
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
    Collector -->|"HTTP 采集"| Source
    ML -->|"读取训练数据"| PG
    ML -->|"模型文件 .pkl"| Models["models/"]
```

## 技术栈

### 后端

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.111+ · Uvicorn · Pydantic v2 |
| 数据库 | PostgreSQL 16 · SQLAlchemy 2.0 (async) · Alembic |
| 缓存 | Redis 7 |
| 认证 | python-jose (JWT) · bcrypt |
| 机器学习 | scikit-learn · XGBoost · statsmodels · pandas · NumPy |
| 数据采集 | httpx · requests · BeautifulSoup4 · lxml |

### 前端

| 类别 | 技术 |
|------|------|
| 框架 | Vue 3.4 (Composition API + `<script setup>`) · TypeScript 5.5 |
| 构建 | Vite 5.3 |
| UI 组件 | Element Plus 2.7 |
| 图表 | ECharts 5.5（含 GeoJSON 地图） |
| 状态管理 | Pinia 2.1 |
| HTTP 客户端 | Axios 1.7 |

### 基础设施

| 类别 | 技术 |
|------|------|
| 容器化 | Docker · Docker Compose（dev overlay + prod 基准） |
| 反向代理 | Nginx 1.27（生产）· Vite Proxy（开发） |
| 测试 | pytest · pytest-asyncio · Playwright |
| 代码质量 | Ruff · mypy · vue-tsc |

## 快速开始

### 环境要求

- [Docker](https://docs.docker.com/get-docker/) 与 [Docker Compose](https://docs.docker.com/compose/install/) v2+
- Git

### 启动项目

```bash
# 1. 克隆仓库
git clone https://github.com/zidou-kiyn/china-housing-price-analysis.git
cd china-housing-price-analysis

# 2. 启动所有服务（开发模式，自动叠加 docker-compose.override.yml）
docker compose up -d --build

# 3. 等待服务就绪（首次启动会自动执行数据库迁移并导入城市种子数据）
docker compose logs -f backend
# 看到 "Uvicorn running on http://0.0.0.0:8000" 即可 Ctrl+C

# 4. 创建管理员账号
docker compose exec backend uv run --no-sync python scripts/create_admin.py admin admin@example.com your_password

# 5. 访问系统
# 前端：http://localhost:5173
# API 文档：http://localhost:5173/api/docs（通过 Vite 代理）
```

### 环境变量

开发模式使用项目根目录的 `.env` 文件，关键配置项：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 异步连接串 | `postgresql+asyncpg://postgres:postgres@postgres:5432/housing_price` |
| `REDIS_URL` | Redis 连接地址 | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | `dev-only-insecure-key`（生产务必替换） |
| `CRAWL_CONCURRENCY` | 采集并发数 | `3` |

生产部署请复制 `.env.prod` 并替换敏感值，使用：

```bash
docker compose -f docker-compose.yml --env-file .env.prod up -d --build
```

<details>
<summary><strong>手动部署（不使用 Docker）</strong></summary>

#### 前置条件

- Python 3.11+（推荐使用 [uv](https://docs.astral.sh/uv/) 管理）
- Node.js 20+
- PostgreSQL 16
- Redis 7

#### 后端

```bash
cd backend

# 安装依赖
uv sync

# 配置环境变量（编辑 DATABASE_URL 等指向本地数据库）
cp ../.env .env
# 编辑 .env，将 postgres / redis 主机名从容器名改为 localhost

# 执行数据库迁移
uv run alembic upgrade head

# 创建管理员
uv run python scripts/create_admin.py admin admin@example.com your_password

# 启动后端（开发模式，热重载）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 前端

```bash
cd frontend

# 安装依赖
npm ci

# 启动开发服务器（自动代理 /api 到 localhost:8000）
npm run dev
```

前端访问 `http://localhost:5173`。

</details>

## 项目结构

```
Urban-Housing-Price-Analysis-System/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST API 路由（auth, cities, prices, analytics, predictions, admin_*）
│   │   ├── collector/       # 数据采集器（数据源适配器、HTTP 客户端、存储）
│   │   ├── core/            # 配置、安全、数据源策略
│   │   ├── ml/              # 机器学习（训练、预测、特征工程、数据集构建）
│   │   ├── models/          # SQLAlchemy ORM 模型
│   │   ├── pipeline/        # 采集管道（清洗、校验、入库）
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   └── services/        # 业务逻辑层
│   ├── alembic/             # 数据库迁移
│   ├── scripts/             # 运维脚本（创建管理员、获取 GeoJSON 等）
│   ├── seed/                # 城市种子数据
│   └── tests/               # 后端测试
├── frontend/
│   └── src/
│       ├── api/             # Axios API 模块
│       ├── components/      # Vue 组件（图表、地图、选择器）
│       ├── composables/     # 组合式函数
│       ├── stores/          # Pinia 状态管理
│       ├── views/           # 页面视图（11 个页面）
│       └── router/          # 路由配置
├── data/                    # 持久化数据（GeoJSON、采集原始数据、数据库文件）
├── docker-compose.yml       # 生产基准配置
├── docker-compose.override.yml  # 开发模式叠加配置
└── .env                     # 开发环境变量
```

## 开源许可

本项目基于 [MIT 许可证](./LICENSE) 开源。
