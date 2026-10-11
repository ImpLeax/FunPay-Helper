import json
from html import escape

import pytest

from app.funpay import parsers
from app.funpay.errors import RequestError, UnauthorizedError

APP_DATA = escape(json.dumps({"userId": 100, "csrf-token": "csrf123", "locale": "en"}))


def page(body: str, logged_in: bool = True) -> str:
    user = '<div class="user-link-name">seller</div>' if logged_in else ""
    return f'<html><body data-app-data="{APP_DATA}">{user}{body}</body></html>'


def test_parse_account_info():
    html = page('<span class="badge badge-trade">3</span><span class="badge badge-orders">1</span>')
    info = parsers.parse_account_info(html)
    assert (info.user_id, info.username, info.csrf_token) == (100, "seller", "csrf123")
    assert (info.active_sales, info.active_purchases) == (3, 1)


def test_parse_account_info_requires_login():
    with pytest.raises(UnauthorizedError):
        parsers.parse_account_info(page("", logged_in=False))


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1 234.50 ₽", (1234.5, "₽")), ("0 $", (0.0, "$")), ("12,5 €", (12.5, "€"))],
)
def test_parse_money(text, expected):
    assert parsers.parse_money(text) == expected


def test_parse_balance_prefers_non_zero():
    html = '<span class="balances-value">0 ₽</span><span class="balances-value">15.5 $</span>'
    assert parsers.parse_balance(html) == (15.5, "$")
    assert parsers.parse_balance("<div></div>") is None


def test_parse_chat_previews():
    html = (
        '<a class="contact-item unread" data-id="5" data-node-msg="77">'
        '<div class="media-user-name">buyer</div>'
        '<div class="contact-item-message">hello</div></a>'
        '<a class="contact-item" data-id="6" data-node-msg="80">'
        '<div class="media-user-name">other</div>'
        '<div class="contact-item-message">ok</div></a>'
    )
    first, second = parsers.parse_chat_previews(html)
    assert (first.chat_id, first.name, first.last_message_id, first.unread) == (
        5,
        "buyer",
        77,
        True,
    )
    assert second.unread is False


def test_parse_chat_messages():
    node = {
        "type": "chat_node",
        "data": {
            "messages": [
                {"id": 1, "author": 0, "html": '<div role="alert">Order paid</div>'},
                {"id": 2, "author": 42, "html": '<div class="chat-msg-text">line1<br>line2</div>'},
                {"id": 3, "author": 42, "html": '<a class="chat-img-link"><img alt="x"></a>'},
            ]
        },
    }
    system, text, image = parsers.parse_chat_messages(node)
    assert (system.author_id, system.text) == (0, "Order paid")
    assert (text.author_id, text.text) == (42, "line1\nline2")
    assert image.text is None


def test_parse_orders_maps_subcategory_and_chat():
    sections = escape(json.dumps([["lot-89", "Accounts"], ["chip-5", "Gold"]]))
    html = page(
        '<select name="game"><option value="">All</option>'
        f'<option value="1" data-data="{sections}">Steam</option></select>'
        '<a class="tc-item info"><div class="tc-order">#ABCD1234</div>'
        '<div class="media-user-name"><span data-href="https://funpay.com/users/42/">buyer</span>'
        '</div><div class="text-muted">Steam, Accounts</div></a>'
    )
    (order,) = parsers.parse_orders(html, own_user_id=100)
    assert order.order_id == "ABCD1234"
    assert (order.buyer_id, order.buyer_username) == (42, "buyer")
    assert order.subcategory_id == 89
    assert order.chat_id == "users-42-100"


def test_parse_my_lots():
    html = page(
        '<a class="tc-item" data-offer="555"><div class="tc-desc-text">Регион УКРАИНА</div></a>'
        '<a class="tc-item"><div class="tc-desc-text">no offer id</div></a>'
    )
    (lot,) = parsers.parse_my_lots(html)
    assert (lot.lot_id, lot.description) == (555, "Регион УКРАИНА")


def test_parse_lot_form_matches_browser_submission():
    html = """
    <form class="form-offer-editor">
      <input name="csrf_token" value="t">
      <input name="offer_id" value="555">
      <input name="query" value="ignored">
      <input type="checkbox" name="active" checked>
      <input type="checkbox" name="auto_delivery">
      <input value="no name">
      <textarea name="secrets">a\nb</textarea>
      <div class="form-group"><select name="server">
        <option value="1">One</option><option value="2" selected>Two</option>
      </select></div>
      <div class="form-group hidden"><select name="hidden_field">
        <option value="x" selected>X</option>
      </select></div>
    </form>
    """
    form = parsers.parse_lot_form(html, 555)
    assert form.fields == {
        "csrf_token": "t",
        "offer_id": "555",
        "active": "on",
        "secrets": "a\nb",
        "server": "2",
    }


def test_parse_lot_form_reports_errors():
    with pytest.raises(RequestError, match="Lot not found"):
        parsers.parse_lot_form('<p class="lead">Lot not found</p>', 1)
