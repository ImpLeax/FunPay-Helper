from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message


class AllowedChatFilter(Filter):
    """Lets through only updates coming from the configured Telegram chat."""

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        message = event.message if isinstance(event, CallbackQuery) else event
        return message is not None and message.chat.id == self.chat_id
