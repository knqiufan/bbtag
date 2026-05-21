"""Shared DeepSeek balance parsing for push_deepseek_balance*.py."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from balance_ratio_common import (
    BalancePanelView,
    CashRatioView,
    format_money_amount,
    format_money_console,
    parse_amount,
)

DEFAULT_BASE_URL = "https://api.deepseek.com"
BALANCE_PATH = "/user/balance"
DEFAULT_CURRENCY = "CNY"

SETTINGS_PATHS = (
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "settings.local.json",
)

ENV_API_KEYS = ("DEEPSEEK_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class DeepSeekBalanceError(RuntimeError):
    """Raised when credentials or balance API calls fail."""


def default_base_url() -> str:
    env = os.getenv("DEEPSEEK_BASE_URL", "").strip()
    return env or DEFAULT_BASE_URL


def _read_settings_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    env = data.get("env")
    if not isinstance(env, dict):
        return {}
    return {k: str(v) for k, v in env.items() if isinstance(v, str) and v.strip()}


def resolve_api_key(
    cli_key: str | None,
    *,
    extra_settings: Path | None = None,
) -> str:
    if cli_key and cli_key.strip():
        return cli_key.strip()

    merged: dict[str, str] = {}
    paths: list[Path] = list(SETTINGS_PATHS)
    if extra_settings is not None:
        paths.append(extra_settings.expanduser())
    for path in paths:
        merged = {**merged, **_read_settings_env(path)}

    for name in ENV_API_KEYS:
        if key := merged.get(name, "").strip():
            return key
    for name in ENV_API_KEYS:
        if key := os.getenv(name, "").strip():
            return key
    raise DeepSeekBalanceError(
        "DEEPSEEK_API_KEY is not set. Configure env.DEEPSEEK_API_KEY in "
        "~/.claude/settings.json, export DEEPSEEK_API_KEY, or pass --api-key."
    )


def pick_balance_info(
    payload: Mapping[str, Any],
    currency: str,
) -> Mapping[str, Any]:
    raw = payload.get("balance_infos")
    if not isinstance(raw, list):
        raise DeepSeekBalanceError("Expected balance_infos array in balance response.")

    target = currency.strip().upper()
    for item in raw:
        if isinstance(item, Mapping) and str(item.get("currency", "")).upper() == target:
            return item

    raise DeepSeekBalanceError(f"No balance_infos entry for currency {target}.")


def parse_balance_payload(
    payload: Mapping[str, Any],
    *,
    currency: str = DEFAULT_CURRENCY,
    fetched_at: datetime | None = None,
) -> BalancePanelView:
    """Map DeepSeek fields: total_balance, granted_balance, topped_up_balance."""
    info = pick_balance_info(payload, currency)
    total = parse_amount(info.get("total_balance"))
    granted = parse_amount(info.get("granted_balance"))
    topped = parse_amount(info.get("topped_up_balance"))
    return BalancePanelView(
        account_type=str(info.get("currency") or currency).upper(),
        balance=total,
        cash_total=topped,
        voucher_total=granted,
        fetched_at=fetched_at or datetime.now().astimezone(),
    )


def _money_symbol(currency: str) -> str:
    return "$" if currency.strip().upper() == "USD" else "¥"


def compute_deepseek_ratio(account: BalancePanelView) -> CashRatioView:
    """DeepSeek ratio: grant / total_balance; bar = grant share; % left = available."""
    symbol = _money_symbol(account.account_type)
    total = account.balance
    granted = account.voucher_total
    topped = account.cash_total

    pool = total if total > 0 else granted + topped

    if pool > 0:
        grant_part = min(granted, pool)
        left_percent = min(100.0, max(0.0, total / pool * 100.0)) if total > 0 else 100.0
        if total > 0:
            used_percent = min(100.0, max(0.0, (total - topped) / total * 100.0))
        else:
            used_percent = min(100.0, max(0.0, granted / pool * 100.0))
    else:
        grant_part = 0.0
        left_percent = 0.0
        used_percent = 0.0

    left_rounded = round(left_percent, 1)
    used_rounded = round(used_percent, 1)
    summary_text = (
        f"{format_money_amount(grant_part, symbol=symbol)} / "
        f"{format_money_amount(pool, symbol=symbol)} "
        f"({left_rounded:.1f}% left)"
    )
    return CashRatioView(
        used_amount=grant_part,
        voucher_total=pool,
        balance=total,
        left_percent=left_rounded,
        used_percent=used_rounded,
        summary_text=summary_text,
    )


def format_ratio_console(ratio: CashRatioView) -> str:
    return (
        f"{format_money_console(ratio.used_amount)} / "
        f"{format_money_console(ratio.voucher_total)} "
        f"({ratio.left_percent:.1f}% left)"
    )


def fetch_balance_json(
    base_url: str,
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{BALANCE_PATH}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "push_deepseek_balance.py",
        "Accept": "application/json",
    }

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise DeepSeekBalanceError(
                "Authentication failed with 401/403. Check your DeepSeek API key."
            ) from exc
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise DeepSeekBalanceError(
            f"DeepSeek API returned HTTP {exc.code}{suffix}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DeepSeekBalanceError(f"Request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DeepSeekBalanceError(f"Failed to parse API response as JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise DeepSeekBalanceError("Expected a JSON object from /user/balance.")
    return payload


__all__ = [
    "BalancePanelView",
    "CashRatioView",
    "DeepSeekBalanceError",
    "DEFAULT_CURRENCY",
    "compute_deepseek_ratio",
    "default_base_url",
    "fetch_balance_json",
    "format_ratio_console",
    "parse_balance_payload",
    "resolve_api_key",
]
