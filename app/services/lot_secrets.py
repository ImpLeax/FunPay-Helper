"""Buyer-facing lot content: secret lines delivered to buyers and region detection.

FunPay buyers of these lots are Russian-speaking, so the strings below are intentionally
in Russian. Changing SECRET_LINE_TEMPLATE breaks parsing of lots that are already listed.
"""

import re
from dataclasses import dataclass

from app.db.models import AccountRegion
from app.db.repository import AccountCredentials

SECRET_LINE_TEMPLATE = (
    "Steam логин: {steam_login} | Steam пароль: {steam_password} | "
    "Почта: {email} | Пароль от почты: {email_password}"
)
_LOGIN_RE = re.compile(r"^Steam логин:\s*(?P<login>.+?)\s*\|")

# Keywords looked up (case-insensitively) in the lot description to pick the stock region.
REGION_KEYWORDS: dict[AccountRegion, str] = {
    AccountRegion.UKR: "УКРАИНА",
    AccountRegion.KAZ: "КАЗАХСТАН",
    AccountRegion.USA: "США",
}


def detect_region(description: str) -> AccountRegion | None:
    upper = description.upper()
    return next((region for region, kw in REGION_KEYWORDS.items() if kw in upper), None)


def format_secret_line(account: AccountCredentials) -> str:
    return SECRET_LINE_TEMPLATE.format(
        steam_login=account.steam_login,
        steam_password=account.steam_password,
        email=account.email,
        email_password=account.email_password,
    )


def split_secrets(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def parse_login(line: str) -> str | None:
    match = _LOGIN_RE.match(line.strip())
    return match.group("login") if match else None


@dataclass(slots=True, frozen=True)
class RestockPlan:
    sold_ids: list[int]
    """SELLING accounts no longer present in any lot: FunPay delivered them."""
    relisted_ids: list[int]
    """UNLISTED accounts found in a lot (e.g. the status update failed after a save)."""


def plan_status_sync(
    listed_logins: set[str],
    selling: dict[int, str],
    unlisted: dict[int, str],
) -> RestockPlan:
    """Compare logins currently in lots with DB statuses (id -> login maps)."""
    return RestockPlan(
        sold_ids=[acc_id for acc_id, login in selling.items() if login not in listed_logins],
        relisted_ids=[acc_id for acc_id, login in unlisted.items() if login in listed_logins],
    )
