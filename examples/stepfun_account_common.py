"""Shared StepFun account parsing for push_stepfun_balance*.py."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Mapping

from balance_ratio_common import (
    AccountView,
    BalancePanelView,
    CashRatioView,
    compute_cash_ratio,
    format_money,
    format_money_amount,
    format_money_console,
    format_ratio_console,
    format_type_label,
    format_updated_text,
    format_updated_text_long,
    parse_amount,
)

DEFAULT_BASE_URL = "https://api.stepfun.com/v1"
ACCOUNTS_PATH = "/accounts"

ENV_API_KEYS = ("STEPFUN_API_KEY", "STEPFUN_TOKEN")

__all__ = [
    "AccountView",
    "BalancePanelView",
    "CashRatioView",
    "StepFunAccountError",
    "compute_cash_ratio",
    "default_base_url",
    "fetch_account_json",
    "format_money",
    "format_money_amount",
    "format_money_console",
    "format_ratio_console",
    "format_type_label",
    "format_updated_text",
    "format_updated_text_long",
    "parse_account_payload",
    "resolve_api_key",
]


class StepFunAccountError(RuntimeError):
    """Raised when credentials or account API calls fail."""


def default_base_url() -> str:
    env = os.getenv("STEPFUN_BASE_URL", "").strip()
    return env or DEFAULT_BASE_URL


def resolve_api_key(cli_key: str | None) -> str:
    if cli_key and cli_key.strip():
        return cli_key.strip()
    for name in ENV_API_KEYS:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise StepFunAccountError(
        "STEPFUN_API_KEY is not set. Export STEPFUN_API_KEY or pass --api-key."
    )


def parse_account_payload(
    payload: Mapping[str, Any],
    *,
    fetched_at: datetime | None = None,
) -> BalancePanelView:
    if payload.get("object") != "account":
        raise StepFunAccountError(
            'Expected JSON object with object="account" from /accounts.'
        )

    account_type = str(payload.get("type") or "unknown")
    return BalancePanelView(
        account_type=account_type,
        balance=parse_amount(payload.get("balance")),
        cash_total=parse_amount(payload.get("total_cash_balance")),
        voucher_total=parse_amount(payload.get("total_voucher_balance")),
        fetched_at=fetched_at or datetime.now().astimezone(),
    )


def fetch_account_json(
    base_url: str,
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{ACCOUNTS_PATH}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "push_stepfun_balance.py",
        "Accept": "application/json",
    }

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise StepFunAccountError(
                "Authentication failed with 401/403. Check your StepFun API key."
            ) from exc
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise StepFunAccountError(f"StepFun API returned HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise StepFunAccountError(f"Request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise StepFunAccountError(f"Failed to parse API response as JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise StepFunAccountError("Expected a JSON object from /accounts.")
    return payload
