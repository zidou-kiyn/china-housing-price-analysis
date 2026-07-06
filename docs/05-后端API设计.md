# 05 · 后端 API 设计

> 本文档为 REST API 的**单一事实源**。改动 API 须先改本文档，再改代码。
> 所有端点前缀：`/api/v1`。

## 1. 总体规范

| 规范 | 说明 |
|------|------|
| 协议 | HTTPS（生产）/ HTTP（开发） |
| 格式 | JSON，`Content-Type: application/json` |
| 分页 | `?page=1&page_size=20`，响应含 `total`、`page`、`page_size` |
| 排序 | `?sort_by=supply_price&sort_order=desc` |
| 日期 | `YYYY-MM`（年月）/ `YYYY-MM-DD`（日期）/ ISO 8601（时间戳） |
| 错误 | 统一 `{"detail": "...", "code": "ERROR_CODE"}` |

## 2. 鉴权

- **方式**：JWT Bearer Token
- **签发**：`POST /auth/login` 成功后返回 `access_token`
- **传递**：`Authorization: Bearer <token>`
- **过期**：access_token 30 分钟
- **密码**：bcrypt 哈希存储（passlib）

### 角色权限矩阵

| 端点类别 | guest (无token) | user | admin |
|---------|:---:|:---:|:---:|
| 元数据 / 均价 / 走势 / 排行 | R | R | R |
| 多区域对比 / 地图 | - | R | R |
| 预测结果 | - | R | R |
| 采集管理 / 模型管理 | - | - | RW |
| 用户管理 | - | - | RW |

## 3. 端点定义

### 3.1 鉴权（Auth）

#### `POST /auth/register`

注册新用户。

**请求体**：
```json
{
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "password": "securePass123"
}
```

**成功响应** `201`：
```json
{
  "id": 1,
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "user"
}
```

**错误** `409`：`{"detail": "用户名已存在", "code": "USERNAME_EXISTS"}`

#### `POST /auth/login`

**请求体**：
```json
{
  "username": "zhangsan",
  "password": "securePass123"
}
```

**成功响应** `200`：
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

**错误** `401`：`{"detail": "用户名或密码错误", "code": "INVALID_CREDENTIALS"}`

#### `GET /auth/me`

获取当前用户信息。需 Bearer Token。

**成功响应** `200`：
```json
{
  "id": 1,
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "user",
  "is_active": true
}
```

### 3.2 元数据（Metadata）

#### `GET /cities`

获取所有城市列表。

**成功响应** `200`：
```json
[
  {"id": 1, "name": "泉州", "code": "qz", "province": "福建"},
  {"id": 2, "name": "厦门", "code": "xm", "province": "福建"}
]
```

#### `GET /cities/{code}/districts`

获取指定城市的区县列表。

**路径参数**：`code` — 城市拼音缩写（如 `qz`）

**成功响应** `200`：
```json
[
  {"id": 1, "city_id": 1, "name": "丰泽区", "code": "fengze"},
  {"id": 2, "city_id": 1, "name": "鲤城区", "code": "licheng"}
]
```

**错误** `404`：`{"detail": "城市不存在", "code": "CITY_NOT_FOUND"}`

### 3.3 行情（Price）

#### `GET /regions/{id}/price`

获取指定区域的最新均价。

**查询参数**：
- `region_type`（必填）：`city` | `district` | `area`

**成功响应** `200`：
```json
{
  "region_type": "district",
  "region_id": 1,
  "region_name": "丰泽区",
  "year_month": "2026-06",
  "supply_price": 14286,
  "attention_price": null,
  "value_price": 8596
}
```

#### `GET /regions/{id}/trend`

获取指定区域的价格走势。

**查询参数**：
- `region_type`（必填）：`city` | `district` | `area`
- `months`（可选，默认 12）：返回最近 N 个月数据
- `price_type`（可选，默认 `supply_price`）：`supply_price` | `attention_price` | `value_price`

**成功响应** `200`：
```json
{
  "region_type": "district",
  "region_id": 1,
  "region_name": "丰泽区",
  "price_type": "supply_price",
  "data": [
    {"year_month": "2025-07", "price": 15200},
    {"year_month": "2025-08", "price": 15100},
    {"year_month": "2026-06", "price": 14286}
  ]
}
```

#### `GET /regions/{id}/distribution`

获取指定区域的价格分布。

**查询参数**：
- `region_type`（必填）
- `year_month`（可选，默认最新）

**成功响应** `200`：
```json
{
  "region_type": "city",
  "region_id": 1,
  "year_month": "2026-06",
  "distribution": [
    {"price_range_low": 5000, "price_range_high": 8000, "percentage": 25.3},
    {"price_range_low": 8000, "price_range_high": 10000, "percentage": 18.7},
    {"price_range_low": 10000, "price_range_high": 15000, "percentage": 32.1}
  ]
}
```

### 3.4 排行与对比（Rank & Compare）

#### `GET /rank`

按均价排行。

**查询参数**：
- `region_type`（必填）：排行粒度
- `city_code`（可选）：限定城市范围
- `sort_by`（可选，默认 `supply_price`）
- `sort_order`（可选，默认 `desc`）
- `page`、`page_size`

**成功响应** `200`：
```json
{
  "total": 8,
  "page": 1,
  "page_size": 20,
  "items": [
    {"region_id": 1, "region_name": "丰泽区", "supply_price": 14286, "value_price": 8596, "yoy_pct": -3.2, "mom_pct": 0.6}
  ]
}
```

#### `GET /compare`

多区域价格对比。需 user 角色。

**查询参数**：
- `region_type`（必填）
- `region_ids`（必填）：逗号分隔，2~5 个 ID
- `months`（可选，默认 12）
- `price_type`（可选，默认 `supply_price`）

**成功响应** `200`：
```json
{
  "price_type": "supply_price",
  "regions": [
    {
      "region_id": 1,
      "region_name": "丰泽区",
      "data": [
        {"year_month": "2025-07", "price": 15200},
        {"year_month": "2026-06", "price": 14286}
      ]
    },
    {
      "region_id": 2,
      "region_name": "鲤城区",
      "data": [
        {"year_month": "2025-07", "price": 12800},
        {"year_month": "2026-06", "price": 12500}
      ]
    }
  ]
}
```

### 3.5 地图（Map）

#### `GET /map/heat`

地图热力数据。需 user 角色。

**查询参数**：
- `city_code`（必填）
- `region_type`（可选，默认 `district`）

**成功响应** `200`：
```json
{
  "city_code": "qz",
  "region_type": "district",
  "data": [
    {"region_id": 1, "region_name": "丰泽区", "price": 14286, "lat": 24.874, "lng": 118.612},
    {"region_id": 2, "region_name": "鲤城区", "price": 12500, "lat": 24.907, "lng": 118.587}
  ]
}
```

### 3.6 预测（Prediction）

#### `GET /predict/{regionId}`

获取预测结果。需 user 角色。

**查询参数**：
- `region_type`（必填）
- `months_ahead`（可选，默认 3）：预测未来 N 月

**成功响应** `200`：
```json
{
  "region_type": "district",
  "region_id": 1,
  "region_name": "丰泽区",
  "model_name": "random_forest",
  "model_version": "v1.0",
  "predictions": [
    {"target_month": "2026-07", "predicted_price": 14100, "confidence_lower": 13500, "confidence_upper": 14700},
    {"target_month": "2026-08", "predicted_price": 13950, "confidence_lower": 13200, "confidence_upper": 14700},
    {"target_month": "2026-09", "predicted_price": 13800, "confidence_lower": 12900, "confidence_upper": 14700}
  ]
}
```

#### `POST /admin/predict/train`

触发模型训练。需 admin 角色。

**请求体**：
```json
{
  "model_name": "random_forest",
  "city_code": "qz",
  "region_type": "district"
}
```

**成功响应** `202`：
```json
{
  "message": "训练任务已提交",
  "model_name": "random_forest",
  "model_version": "v1.1"
}
```

### 3.7 采集管理（Admin / Crawl）

#### `POST /admin/crawl/trigger`

手动触发采集任务。需 admin 角色。

**请求体**：
```json
{
  "source": "creprice",
  "city_code": "qz",
  "job_type": "full"
}
```

**成功响应** `202`：
```json
{
  "job_id": 42,
  "status": "pending",
  "message": "采集任务已创建"
}
```

#### `GET /admin/crawl/jobs`

查看采集任务列表。需 admin 角色。

**查询参数**：`page`、`page_size`、`status`（可选过滤）

**成功响应** `200`：
```json
{
  "total": 15,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 42,
      "source": "creprice",
      "city_code": "qz",
      "job_type": "full",
      "status": "completed",
      "started_at": "2026-07-01T02:00:00Z",
      "finished_at": "2026-07-01T02:05:30Z"
    }
  ]
}
```

## 4. 错误码

| HTTP 状态 | code | 说明 |
|-----------|------|------|
| 400 | VALIDATION_ERROR | 请求参数校验失败 |
| 401 | INVALID_CREDENTIALS | 用户名或密码错误 |
| 401 | TOKEN_EXPIRED | Token 已过期 |
| 401 | TOKEN_INVALID | Token 无效 |
| 403 | PERMISSION_DENIED | 无权限访问 |
| 404 | CITY_NOT_FOUND | 城市不存在 |
| 404 | REGION_NOT_FOUND | 区域不存在 |
| 404 | PREDICTION_NOT_FOUND | 暂无预测数据 |
| 409 | USERNAME_EXISTS | 用户名已存在 |
| 409 | EMAIL_EXISTS | 邮箱已存在 |
| 500 | INTERNAL_ERROR | 服务端内部错误 |

## 5. 通用响应包装

成功响应直接返回数据（无额外包装层），依赖 HTTP 状态码判断成败。分页接口返回 `{total, page, page_size, items}`。
