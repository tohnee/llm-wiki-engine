"""调度器独立进程入口。

启动方式:
  python -m app.maintain.scheduler                              # 单次按 SCHEDULE_INTERVAL_SEC 循环
  SCHEDULE_INTERVAL_SEC=3600 python -m app.maintain.scheduler   # 每小时跑一次
  python -m app.maintain.scheduler t1 t2                        # 仅跑指定租户

进程内做的事:
  1. 启动安全闸门(占位密钥/默认 DSN 校验,生产强约束)
  2. 注册 v2 hook handlers(含 on_schedule)
  3. 进入 run_scheduler() 循环,周期 emit(ON_SCHEDULE)
"""
from __future__ import annotations

import asyncio
import sys


async def main(argv: list[str]) -> None:
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets(required_keys=("INTERNAL_HMAC_SECRET",))

    # 触发 handler 注册
    import app.core.hook_handlers  # noqa: F401

    from app.db.store import Store
    from app.compile.dag import CompileBus
    from app.maintain.cycle import run_scheduler

    store = await Store.connect()
    try:
        bus = await CompileBus.connect()
    except Exception as e:
        print(f"[scheduler] CompileBus unavailable, running without human-review queue: {e}", flush=True)
        bus = None

    tenants = argv[1:] if len(argv) > 1 else None
    await run_scheduler(store, bus=bus, tenants=tenants)


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv))
    except KeyboardInterrupt:
        print("[scheduler] stopped by user", flush=True)
