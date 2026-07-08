# 执行清单：NBS 指数导入与月度赋形

## 顺序步骤

### Step 1 — 数据层
- [x] 先实测下载 CSV 抽样，核对列名/城市英文名/月份格式与 city.name 实际值
      （2026-07-08 实测：70 个英文城市名、year/month 整数列、两指数列无缺失
      无越界无重复键；70 个对应中文名全部在 city 表有同名行）
- [x] 迁移 006 + PriceIndexSnapshot 模型（up/down/up 已实测）
- [x] index_import.py：下载/解析/crosswalk/幂等 upsert/统计返回
- [x] POST /admin/collect/import-index（job_runner 异步 job）+ DataManageView 导入按钮

### Step 2 — ML 赋形
- [x] select_index_snapshots 服务函数（price_select.py，默认二手环比）
- [x] dataset.py：index_rows 可选参数、_shape_with_index（链式+几何渐变对齐、
      段级线性回退）、DatasetMeta.shaping 统计
- [x] train/predict 两个调用点供数接线（predictions.py::_load_index_rows）

### Step 3 — 测试与实操
- [x] 单测：解析、crosswalk 未匹配、幂等、赋形数值（手算小例：锚点保持/
      形状随指数/缺失回退）、shaping 统计、index_rows=None 回归
- [x] 实操：导入真实 CSV（70 城 25900 行 2011-01~2026-05，重跑幂等）→
      北京 2019 插值段随指数起伏（非直线），2018/2019/2020-12 锚点值与线性版
      逐位相等
- [x] 重训 RF 一次（v1.8，未激活），metrics_real_monthly 不劣化：
      MAPE 2.71→2.70、MAE 322.79→304.83、R² 0.9376→0.9537
      （headline mape 0.25→0.31：指数形状比直线更难拟合，属预期）
- [x] 全量 pytest（345 passed）+ ruff + 前端 build（vue-tsc）通过

## 验证命令

```bash
docker compose exec -T backend uv run pytest tests/ -x -q \
  --ignore=tests/pipeline/test_runner_live.py --ignore=tests/collector/test_creprice_live.py
docker compose exec -T postgres psql -U postgres -d housing_price \
  -c "SELECT dwelling_type, count(*), min(year_month), max(year_month) FROM price_index_snapshot GROUP BY 1;"
```

## 回滚点

- 迁移可 down；赋形有 index_rows=None 与段级回退双保险。

## 审查门

- Step 2 后自查赋形数值：锚点月值必须与校准年度值精确相等；段内单调性不强求
  （形状忠于指数）。
