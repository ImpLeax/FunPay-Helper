from aiogram import Router

from app.bot.filters import AllowedChatFilter

from . import accounts, common, settings, stats


def build_router(chat_id: int) -> Router:
    """Combine all routers; everything except /chatid is limited to the configured chat."""
    restricted = Router(name="restricted")
    restricted.message.filter(AllowedChatFilter(chat_id))
    restricted.callback_query.filter(AllowedChatFilter(chat_id))
    restricted.include_routers(common.router, stats.router, settings.router, accounts.router)

    root = Router(name="root")
    root.include_routers(common.public_router, restricted)
    return root
