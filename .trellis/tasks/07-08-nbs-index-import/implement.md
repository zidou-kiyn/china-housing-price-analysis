# 执行清单：NBS 指数导入与月度赋形

## 顺序步骤

### Step 1 — 数据层
- [ ] 先实测下载 CSV 抽样，核对列名/城市英文名/月份格式与 city.name 实际值
- [ ] 迁移 006 + PriceIndexSnapshot 模型
- [ ] index_import.py：下载/解析/crosswalk/幂等 upsert/统计返回
- [ ] POST /admin/collect/import-index + DataManageView 导入按钮

### Step 2 — ML 赋形
- [ ] select_index_snapshots 服务函数（price_select.py）
- [ ] dataset.py：index_rows 可选参数、_shape_with_index（链式+几何渐变对齐、
      段级线性回退）、DatasetMeta.shaping 统计
- [ ] train/predict 两个调用点供数接线

### Step 3 — 测试与实操
- [ ] 单测：解析、crosswalk 未匹配、幂等、赋形数值（手算小例：锚点保持/
      形状随指数/缺失回退）、shaping 统计、index_rows=None 回归
- [ ] 实操：导入真实 CSV → 核对北京插值段不再是直线且锚点不变
- [ ] 重训 RF 一次，对比 metrics_real_monthly（不劣化或有解释）
- [ ] 全量 pytest + ruff + 前端 build

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
