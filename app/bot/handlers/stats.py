import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.texts import error_text, stats_text, stock_text
from app.db.repository import AccountRepository
from app.funpay import FunPayClient

logger = logging.getLogger(__name__)
router = Router(name="stats")


@router.message(Command("stats"))
async def stats(message: Message, funpay: FunPayClient, accounts: AccountRepository) -> None:
    status = await message.answer("🔄 Pulling the latest stats from FunPay...")
    try:
        account = await funpay.refresh()
        stock = await accounts.get_stock_stats()
    except Exception as e:
        logger.exception("Failed to build /stats")
        await status.edit_text(error_text("Error retrieving statistics:", e))
        return
    await status.edit_text(stats_text(account, stock))


@router.message(Command("stock"))
async def stock(message: Message, accounts: AccountRepository) -> None:
    try:
        text = stock_text(await accounts.get_stock_stats())
    except Exception as e:
        logger.exception("Failed to build /stock")
        text = error_text("Error retrieving stock data:", e)
    await message.answer(text)
