from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import ToggleCallback, settings_keyboard
from app.bot.texts import settings_text
from app.services.runtime_settings import RuntimeSettings

router = Router(name="settings")


@router.message(Command("settings"))
async def show_settings(message: Message, runtime_settings: RuntimeSettings) -> None:
    await message.answer(settings_text(runtime_settings), reply_markup=settings_keyboard())


@router.callback_query(ToggleCallback.filter())
async def toggle(
    call: CallbackQuery, callback_data: ToggleCallback, runtime_settings: RuntimeSettings
) -> None:
    if callback_data.feature == "restock":
        enabled = await runtime_settings.toggle_auto_restock()
        label = "Auto-Restock"
    else:
        enabled = await runtime_settings.toggle_auto_reply()
        label = "Auto-Reply"

    if isinstance(call.message, Message):
        await call.message.edit_text(
            settings_text(runtime_settings), reply_markup=settings_keyboard()
        )
    await call.answer(f"{label} turned {'ON' if enabled else 'OFF'}")
