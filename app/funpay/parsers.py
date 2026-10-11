"""Pure parsing functions that turn FunPay HTML/JSON responses into models."""

import json
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, Tag

from .errors import RequestError, UnauthorizedError
from .models import AccountInfo, ChatMessage, ChatPreview, LotForm, MyLot, Order

_USER_ID_IN_URL = re.compile(r"/users/(\d+)/?")
_WHITESPACE = re.compile(r"\s+")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _text(tag: Tag | None) -> str:
    return tag.get_text(strip=True) if tag else ""


def _int_or_zero(tag: Tag | None) -> int:
    text = _text(tag)
    return int(text) if text.isdigit() else 0


def _app_data(soup: BeautifulSoup) -> dict:
    body = soup.find("body")
    raw = body.get("data-app-data") if isinstance(body, Tag) else None
    if not raw:
        raise RequestError("Page has no data-app-data attribute")
    return json.loads(raw)


def _ensure_logged_in(soup: BeautifulSoup) -> None:
    if soup.find("div", class_="user-link-name") is None:
        raise UnauthorizedError("FunPay page is not authenticated (golden_key invalid or expired)")


def parse_money(text: str) -> tuple[float, str]:
    """Parse strings like '1 234.50 ₽' into (1234.5, '₽')."""
    amount, _, currency = text.strip().rpartition(" ")
    if not amount:
        amount, currency = currency, ""
    return float(_WHITESPACE.sub("", amount).replace(",", ".")), currency


def private_chat_id(user_a: int, user_b: int) -> str:
    low, high = sorted((user_a, user_b))
    return f"users-{low}-{high}"


def parse_csrf_token(html: str) -> str | None:
    try:
        return _app_data(_soup(html)).get("csrf-token")
    except (RequestError, ValueError):
        return None


def parse_account_info(html: str) -> AccountInfo:
    soup = _soup(html)
    _ensure_logged_in(soup)
    app_data = _app_data(soup)
    return AccountInfo(
        user_id=int(app_data["userId"]),
        username=_text(soup.find("div", class_="user-link-name")),
        csrf_token=app_data["csrf-token"],
        active_sales=_int_or_zero(soup.select_one("span.badge.badge-trade")),
        active_purchases=_int_or_zero(soup.select_one("span.badge.badge-orders")),
    )


def parse_balance(html: str) -> tuple[float, str] | None:
    """Return the first non-zero balance on the finances page (or the first if all are zero)."""
    balances = [
        parse_money(text)
        for el in _soup(html).find_all("span", class_="balances-value")
        if (text := el.get_text(strip=True))
    ]
    if not balances:
        return None
    return next((b for b in balances if b[0] > 0), balances[0])


def parse_chat_previews(html: str) -> list[ChatPreview]:
    previews = []
    for item in _soup(html).find_all("a", class_="contact-item"):
        previews.append(
            ChatPreview(
                chat_id=int(item["data-id"]),
                name=_text(item.find("div", class_="media-user-name")),
                last_message_text=_text(item.find("div", class_="contact-item-message")),
                last_message_id=int(item.get("data-node-msg") or 0),
                unread="unread" in item.get("class", []),
            )
        )
    return previews


def find_runner_object(objects: Iterable[dict], object_type: str) -> dict | None:
    return next((obj for obj in objects if obj.get("type") == object_type), None)


def parse_chat_messages(chat_node: dict) -> list[ChatMessage]:
    data = chat_node.get("data") or {}
    messages = []
    for raw in data.get("messages") or []:
        soup = _soup(raw.get("html", "").replace("<br>", "\n"))
        text_div = soup.find("div", class_="chat-msg-text") or soup.find("div", role="alert")
        messages.append(
            ChatMessage(
                message_id=int(raw["id"]),
                author_id=int(raw.get("author") or 0),
                text=text_div.get_text().strip() if text_div else None,
            )
        )
    return messages


def _subcategory_ids_by_name(soup: BeautifulSoup) -> dict[str, int]:
    """Map 'Game, Section' labels on the orders page to lot subcategory ids."""
    result: dict[str, int] = {}
    select = soup.find("select", attrs={"name": "game"})
    if not isinstance(select, Tag):
        return result
    for option in select.find_all("option"):
        sections = option.get("data-data")
        if not option.get("value") or not sections:
            continue
        game = option.get_text(strip=True)
        for key, section in json.loads(sections):
            kind, _, section_id = key.partition("-")
            if kind == "lot" and section_id.isdigit():
                result[f"{game}, {section}"] = int(section_id)
    return result


def parse_orders(html: str, own_user_id: int) -> list[Order]:
    soup = _soup(html)
    _ensure_logged_in(soup)
    subcategories = _subcategory_ids_by_name(soup)

    orders = []
    for item in soup.find_all("a", class_="tc-item"):
        buyer = item.select_one("div.media-user-name span")
        match = _USER_ID_IN_URL.search(buyer.get("data-href", "")) if buyer else None
        if not buyer or not match:
            continue
        buyer_id = int(match.group(1))
        subcategory_name = _text(item.find("div", class_="text-muted"))
        orders.append(
            Order(
                order_id=_text(item.find("div", class_="tc-order")).lstrip("#"),
                buyer_id=buyer_id,
                buyer_username=_text(buyer),
                subcategory_name=subcategory_name,
                subcategory_id=subcategories.get(subcategory_name),
                chat_id=private_chat_id(buyer_id, own_user_id),
            )
        )
    return orders


def parse_my_lots(html: str) -> list[MyLot]:
    soup = _soup(html)
    _ensure_logged_in(soup)
    return [
        MyLot(
            lot_id=int(item["data-offer"]),
            description=_text(item.find("div", class_="tc-desc-text")),
        )
        for item in soup.find_all("a", class_="tc-item")
        if item.get("data-offer")
    ]


def parse_lot_form(html: str, lot_id: int) -> LotForm:
    """Collect the lot editor form the way a browser would submit it."""
    soup = _soup(html)
    form = soup.find("form", class_="form-offer-editor")
    if not isinstance(form, Tag):
        error = _text(soup.find("p", class_="lead")) or "lot editor form not found"
        raise RequestError(f"Cannot open lot {lot_id}: {error}")

    fields: dict[str, str] = {}
    for el in form.find_all("input"):
        name = el.get("name")
        if not name or name == "query":
            continue
        if el.get("type") in ("checkbox", "radio"):
            if el.has_attr("checked"):
                fields[name] = el.get("value") or "on"
        else:
            fields[name] = el.get("value") or ""

    for el in form.find_all("textarea"):
        if name := el.get("name"):
            fields[name] = el.get_text()

    for el in form.find_all("select"):
        name = el.get("name")
        group = el.find_parent(class_="form-group")
        if not name or (group and "hidden" in group.get("class", [])):
            continue
        selected = el.find("option", selected=True) or el.find("option")
        if selected is not None:
            fields[name] = selected.get("value", "")

    return LotForm(lot_id=lot_id, fields=fields)
