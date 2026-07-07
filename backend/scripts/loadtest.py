"""简易压测脚本：asyncio + httpx 并发打点，输出 RPS 与延迟分位。

用法：
    .venv/bin/python scripts/loadtest.py --duration 15 --concurrency 20
    .venv/bin/python scripts/loadtest.py --endpoints /health /api/v1/cities

有错误请求时退出码为 1。
"""

import argparse
import asyncio
import statistics
import time

import httpx

DEFAULT_ENDPOINTS = [
    "/health",
    "/api/v1/cities",
    "/api/v1/rank?region_type=district&city_code=qz",
]


async def worker(
    client: httpx.AsyncClient,
    endpoints: list[str],
    deadline: float,
    latencies: dict[str, list[float]],
    errors: dict[str, int],
) -> None:
    i = 0
    while time.perf_counter() < deadline:
        path = endpoints[i % len(endpoints)]
        i += 1
        t0 = time.perf_counter()
        try:
            resp = await client.get(path)
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code >= 400:
                errors[path] = errors.get(path, 0) + 1
            else:
                latencies.setdefault(path, []).append(elapsed)
        except httpx.HTTPError:
            errors[path] = errors.get(path, 0) + 1


def _pct(values: list[float], p: float) -> float:
    return statistics.quantiles(values, n=100)[int(p) - 1] if len(values) >= 2 else values[0]


async def run(base_url: str, endpoints: list[str], duration: float, concurrency: int) -> int:
    latencies: dict[str, list[float]] = {}
    errors: dict[str, int] = {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        deadline = time.perf_counter() + duration
        t_start = time.perf_counter()
        await asyncio.gather(
            *(worker(client, endpoints, deadline, latencies, errors) for _ in range(concurrency))
        )
        elapsed = time.perf_counter() - t_start

    total_ok = sum(len(v) for v in latencies.values())
    total_err = sum(errors.values())
    print(f"\n== 压测结果 base={base_url} 并发={concurrency} 时长={elapsed:.1f}s ==")
    print(f"{'endpoint':<50} {'ok':>6} {'err':>4} {'rps':>7} {'p50ms':>7} {'p95ms':>7} {'maxms':>7}")
    for path in endpoints:
        vals = latencies.get(path, [])
        err = errors.get(path, 0)
        if not vals:
            print(f"{path:<50} {0:>6} {err:>4}       -       -       -       -")
            continue
        print(
            f"{path:<50} {len(vals):>6} {err:>4} {len(vals) / elapsed:>7.1f}"
            f" {_pct(vals, 50):>7.1f} {_pct(vals, 95):>7.1f} {max(vals):>7.1f}"
        )
    print(f"总计: {total_ok} ok / {total_err} err, 整体 RPS {total_ok / elapsed:.1f}")
    return 1 if total_err else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="简易 HTTP 压测")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration", type=float, default=15.0, help="压测时长（秒）")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--endpoints", nargs="*", default=DEFAULT_ENDPOINTS)
    args = parser.parse_args()
    return asyncio.run(run(args.base_url, args.endpoints, args.duration, args.concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
