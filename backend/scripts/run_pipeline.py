"""手动触发采集管线：按城市代码依次执行 采集→清洗→入库→缓存失效。

用法：
    .venv/bin/python scripts/run_pipeline.py qz            # 单城市
    .venv/bin/python scripts/run_pipeline.py xm fz         # 多城市依次执行

城市代码见 city 表（creprice 代码，如 泉州=qz、厦门=xm、福州=fz）。
creprice 请求间隔 1~3s，单城市约 1~2 分钟。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import setup_logging
from app.pipeline.runner import PipelineRunner


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    setup_logging(settings.log_level)
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    runner = PipelineRunner(session_factory)

    failed = []
    try:
        for city_code in sys.argv[1:]:
            print(f"\n== 采集 {city_code} ==")
            try:
                stats = await runner.run("creprice", city_code)
                print(
                    f"完成: snapshots={stats['snapshots']} "
                    f"distributions={stats['distributions']} logs={stats['logs']}"
                )
            except Exception as exc:  # 单城市失败不影响后续城市
                failed.append(city_code)
                print(f"失败: {exc}")
    finally:
        await engine.dispose()

    if failed:
        print(f"\n失败城市: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
