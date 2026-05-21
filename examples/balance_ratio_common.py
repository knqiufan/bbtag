"""Shared balance panel model and ratio formatting for provider push scripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class BalancePanelView:
    account_type: str
    balance: float
    cash_total: float
    voucher_total: float
    fetched_at: datetime


AccountView = BalancePanelView


@dataclass(frozen=True, slots=True)
class CashRatioView:
    """Bar fill uses used_percent (black = used portion of voucher pool)."""

    used_amount: float
    voucher_total: float
    balance: float
    left_percent: float
    used_percent: float
    summary_text: str


def _to_float(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def parse_amount(value: Any) -> float:
    """Parse API amount fields (float or numeric string)."""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0.0
        try:
            return float(stripped)
        except ValueError:
            return 0.0
    return _to_float(value)


def format_money(value: float, *, symbol: str = "¥") -> str:
    return f"{symbol}{value:,.2f}"


def format_money_amount(value: float, *, symbol: str = "¥") -> str:
    return f"{symbol}{value:.2f}"


def format_money_console(value: float) -> str:
    return f"CNY {value:,.2f}"


def format_type_label(account_type: str) -> str:
    normalized = account_type.strip().lower()
    if normalized in ("prepaid", "postpaid"):
        return normalized
    if normalized in ("cny", "usd"):
        return normalized.upper()
    return normalized or "unknown"


def compute_cash_ratio(account: BalancePanelView) -> CashRatioView:
    """Ratio line: used/voucher; % left = balance/voucher."""
    balance = account.balance
    voucher = account.voucher_total

    if voucher > 0:
        used = voucher - balance
        if used < 0:
            used = 0.0
        left_percent = min(100.0, max(0.0, balance / voucher * 100.0))
        used_percent = min(100.0, max(0.0, used / voucher * 100.0))
    else:
        used = 0.0
        left_percent = 0.0
        used_percent = 0.0

    left_rounded = round(left_percent, 1)
    used_rounded = round(used_percent, 1)
    summary_text = (
        f"{format_money_amount(used)} / {format_money_amount(voucher)} "
        f"({left_rounded:.1f}% left)"
    )
    return CashRatioView(
        used_amount=used,
        voucher_total=voucher,
        balance=balance,
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


def format_updated_text(fetched_at: datetime) -> str:
    local = fetched_at.astimezone()
    return f"updated {local.strftime('%H:%M')}"


def format_updated_text_long(fetched_at: datetime) -> str:
    local = fetched_at.astimezone()
    return f"updated {local.strftime('%Y-%m-%d %H:%M')}"
