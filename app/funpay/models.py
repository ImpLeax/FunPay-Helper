from dataclasses import dataclass, field

SYSTEM_AUTHOR_ID = 0
"""FunPay uses author id 0 for system notifications (order paid, review left, etc.)."""


@dataclass(slots=True)
class AccountInfo:
    user_id: int
    username: str
    csrf_token: str
    active_sales: int = 0
    active_purchases: int = 0
    balance: float = 0.0
    currency: str = ""


@dataclass(slots=True, frozen=True)
class ChatPreview:
    chat_id: int
    name: str
    last_message_text: str
    last_message_id: int
    unread: bool


@dataclass(slots=True, frozen=True)
class ChatMessage:
    message_id: int
    author_id: int
    text: str | None
    """None for non-text messages such as images."""


@dataclass(slots=True, frozen=True)
class Order:
    order_id: str
    buyer_id: int
    buyer_username: str
    subcategory_name: str
    subcategory_id: int | None
    chat_id: str


@dataclass(slots=True, frozen=True)
class MyLot:
    lot_id: int
    description: str


@dataclass(slots=True)
class LotForm:
    """Raw form fields of a lot editor page, sent back as-is when saving."""

    lot_id: int
    fields: dict[str, str] = field(default_factory=dict)
