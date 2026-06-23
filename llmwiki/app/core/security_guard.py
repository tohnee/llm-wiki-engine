"""启动期安全闸门:阻止生产环境带着默认密钥/默认 DSN 上线。

判定生产的依据:环境变量 APP_ENV=prod / production / staging。
开发(默认/dev/test)允许使用占位值,只打印告警。

校验项:
  1. JWT_SECRET 不能是 change-me / dev-* 占位
  2. INTERNAL_HMAC_SECRET 同上
  3. PLATFORM_ADMIN_KEY 同上(admin 服务用)
  4. PG_DSN 不能是 llmwiki:llmwiki@localhost 默认值
  5. 密钥长度 ≥ 32(防爆破)

所有服务 lifespan 启动时调用一次 enforce_production_secrets()。
"""
from __future__ import annotations

import os
import sys
from typing import Iterable

_PLACEHOLDER_SECRETS: set[str] = {
    "change-me", "change-me-in-prod", "changeme",
    "dev", "dev-jwt-secret", "dev-internal-secret", "dev-admin-key",
    "test", "test-secret", "secret", "default", "",
}

_DEFAULT_DSN_HINTS: tuple[str, ...] = (
    "llmwiki:llmwiki@localhost",
    "postgres:postgres@localhost",
    "user:password@",
)


def is_production() -> bool:
    env = os.getenv("APP_ENV", "dev").lower()
    return env in {"prod", "production", "staging"}


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    return value.strip().lower() in _PLACEHOLDER_SECRETS


def _violations(*, required_keys: Iterable[str], min_len: int = 32) -> list[str]:
    errs: list[str] = []
    for key in required_keys:
        val = os.getenv(key, "")
        if _is_placeholder(val):
            errs.append(f"{key} 仍为占位/默认值,生产环境必须改为强随机(openssl rand -hex 32)")
        elif len(val) < min_len:
            errs.append(f"{key} 长度 {len(val)} < {min_len},建议 ≥ {min_len} 字符")
    dsn = os.getenv("PG_DSN", "")
    if any(h in dsn for h in _DEFAULT_DSN_HINTS):
        errs.append(f"PG_DSN 命中默认凭证 ({dsn[:40]}…),生产环境必须改为独立账号 + 强密码")
    return errs


def enforce_production_secrets(
    *, required_keys: Iterable[str] = ("JWT_SECRET", "INTERNAL_HMAC_SECRET"),
    extra_required: Iterable[str] = (),
) -> None:
    """生产模式下,若发现占位密钥或默认 DSN,直接退出进程;
    开发模式下,只打印警告,不中断。"""
    keys = list(required_keys) + list(extra_required)
    errs = _violations(required_keys=keys)
    if not errs:
        return
    if is_production():
        print("[security_guard] FATAL: 生产环境检测到不安全配置:", file=sys.stderr, flush=True)
        for e in errs:
            print(f"  - {e}", file=sys.stderr, flush=True)
        print("[security_guard] 请设置 APP_ENV=dev 仅用于本地开发,或修复以上配置后重启。",
              file=sys.stderr, flush=True)
        sys.exit(78)  # EX_CONFIG
    # dev 模式:打印警告但不阻断
    print("[security_guard] WARNING: 当前使用占位密钥/默认 DSN(仅适合本地开发):", flush=True)
    for e in errs:
        print(f"  - {e}", flush=True)
