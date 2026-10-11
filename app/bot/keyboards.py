from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class ToggleCallback(CallbackData, prefix="toggle"):
    feature: str  # "restock" | "reply"


class AddAccountsCallback(CallbackData, prefix="addaccs"):
    confirm: bool


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Toggle Restock",
                    callback_data=ToggleCallback(feature="restock").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Toggle Auto-Reply",
                    callback_data=ToggleCallback(feature="reply").pack(),
                )
            ],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm", callback_data=AddAccountsCallback(confirm=True).pack()
                ),
                InlineKeyboardButton(
                    text="❌ Cancel", callback_data=AddAccountsCallback(confirm=False).pack()
                ),
            ]
        ]
    )
