from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot.texts import START_TEXT

router = Router(name="common")
public_router = Router(name="public")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(START_TEXT)


@public_router.message(Command("chatid"))
async def chat_id(message: Message) -> None:
    """Helps fill CHAT_ID / THREAD_ID in .env during setup; works in any chat."""
    await message.answer(
        f"Chat ID: <code>{message.chat.id}</code>\n"
        f"Thread ID: <code>{message.message_thread_id}</code>"
    )
