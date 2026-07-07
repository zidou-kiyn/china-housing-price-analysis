# 执行计划 - 清洗管线与入库

## 执行清单

- [x] 1. `pipeline/cleaners.py` — 纯函数：`clean_price_timeline(records)` 和 `clean_price_distribution(records, year_month)`
- [x] 2. `pipeline/loaders.py` — async upsert 函数：`upsert_cities`、`upsert_districts`、`upsert_price_snapshots`、`upsert_price_distributions`、`create_crawl_job`、`finish_crawl_job`、`create_crawl_log`
- [x] 3. `pipeline/runner.py` — `PipelineRunner` 编排器，串联 fetch → clean → load → log 流程
- [x] 4. `tests/pipeline/test_cleaners.py` — 清洗逻辑单元测试（10 tests passed）
- [ ] 5. `tests/pipeline/test_loaders.py` — upsert 逻辑测试（需要 PostgreSQL）
- [x] 6. `tests/pipeline/test_runner_live.py` — 集成冒烟测试已编写（@pytest.mark.slow，需 PostgreSQL + 网络验证）

## 关键实现细节

### cleaners.py

```python
def clean_price_timeline(records: list[dict]) -> list[dict]:
    """过滤全 None 行、范围异常价格"""
    
def clean_price_distribution(records: list[dict], year_month: str) -> list[dict]:
    """过滤 percentage=0、low>=high，添加 year_month 字段"""
```

### loaders.py

- 所有函数接收 `AsyncSession` 参数
- upsert 使用 `sqlalchemy.dialects.postgresql.insert` + `on_conflict_do_update`
- `upsert_cities` 返回 `dict[str, int]`（code → id 映射）
- `upsert_districts` 返回 `dict[tuple[str,str], int]`（(city_code, dist_code) → id 映射）

### runner.py

```python
class PipelineRunner:
    def __init__(self, session_factory, redis_client=None):
        ...
    
    async def run(self, source_name: str, city_code: str) -> CrawlJob:
        """端到端执行，返回 crawl_job 记录"""
```

## 验证

```bash
cd backend
uv run pytest tests/pipeline/test_cleaners.py -v
uv run pytest tests/pipeline/test_runner_live.py -v -m slow  # 需要 PostgreSQL + 网络
```
