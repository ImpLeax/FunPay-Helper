import asyncio
import html
import logging

from aiogram import Bot

from app.funpay import FunPayClient
from app.funpay.models import SYSTEM_AUTHOR_ID, ChatPreview

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10
ERROR_BACKOFF = 30


class ChatNotifier:
    """Forwards new buyer messages from FunPay chats to the Telegram group."""

    def __init__(self, funpay: FunPayClient, bot: Bot, chat_id: int, thread_id: int | None) -> None:
        self._funpay = funpay
        self._bot = bot
        self._chat_id = chat_id
        self._thread_id = thread_id
        # Last message id seen per chat; bounded by the number of chats.
        self._seen: dict[int, int] = {}

    async def run(self) -> None:
        while True:
            try:
                await self._poll_once()
                await asyncio.sleep(POLL_INTERVAL)
            except Exception:
                logger.exception("Chat polling failed")
                await asyncio.sleep(ERROR_BACKOFF)

    async def _poll_once(self) -> None:
        for chat in await self._funpay.get_chats():
            if not chat.unread or self._seen.get(chat.chat_id) == chat.last_message_id:
                continue

            messages = await self._funpay.get_chat_messages(chat.chat_id)
            if messages:
                last = messages[-1]
                if last.author_id not in (self._funpay.user_id, SYSTEM_AUTHOR_ID):
                    await self._notify(chat, last.text)
            self._seen[chat.chat_id] = chat.last_message_id

    async def _notify(self, chat: ChatPreview, text: str | None) -> None:
        body = text if text is not None else "[image]"
        await self._bot.send_message(
            chat_id=self._chat_id,
            message_thread_id=self._thread_id,
            text=(
                f"💬 <b>New message from {html.escape(chat.name)}:</b>\n\n"
                f"<i>{html.escape(body)}</i>\n\n"
                f"<a href='https://funpay.com/chat/?node={chat.chat_id}'>🔗 Go to chat</a>"
            ),
            disable_web_page_preview=True,
        )
