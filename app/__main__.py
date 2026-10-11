import asyncio
import logging
from collections.abc import Coroutine

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.handlers import build_router
from app.config import get_settings
from app.db.crypto import PasswordCipher
from app.db.repository import AccountRepository, SettingsRepository, create_engine, init_models
from app.funpay import FunPayClient
from app.logging_setup import setup_logging
from app.services.chat_notifier import ChatNotifier
from app.services.restocker import Restocker
from app.services.review_requester import ReviewRequester
from app.services.runtime_settings import RuntimeSettings

logger = logging.getLogger("app")

SESSION_REFRESH_INTERVAL = 40 * 60


async def keep_session_alive(funpay: FunPayClient) -> None:
    """FunPay sessions expire, so reload account data periodically."""
    while True:
        await asyncio.sleep(SESSION_REFRESH_INTERVAL)
        try:
            await funpay.refresh()
        except Exception:
            logger.exception("Periodic FunPay session refresh failed")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_dir)

    engine = create_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await init_models(engine)

    cipher = PasswordCipher(settings.encryption_key.get_secret_value())
    accounts = AccountRepository(session_factory, cipher)
    runtime_settings = RuntimeSettings(SettingsRepository(session_factory))
    await runtime_settings.load()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(settings.chat_id))

    try:
        await run_bot(bot, dispatcher, accounts, runtime_settings)
    finally:
        await bot.session.close()
        await engine.dispose()
        logger.info("Shut down")


async def run_bot(
    bot: Bot,
    dispatcher: Dispatcher,
    accounts: AccountRepository,
    runtime_settings: RuntimeSettings,
) -> None:
    settings = get_settings()
    async with FunPayClient(
        settings.golden_key.get_secret_value(), settings.funpay_user_agent
    ) as funpay:
        account = await funpay.refresh()
        logger.info("Logged in to FunPay as %s", account.username)

        dispatcher.workflow_data.update(
            funpay=funpay, accounts=accounts, runtime_settings=runtime_settings
        )
        services: list[Coroutine] = [
            keep_session_alive(funpay),
            ChatNotifier(funpay, bot, settings.chat_id, settings.thread_id).run(),
            ReviewRequester(funpay, runtime_settings, settings.steam_subcategory_id).run(),
            Restocker(
                funpay,
                accounts,
                runtime_settings,
                settings.steam_subcategory_id,
                settings.max_lot_stock,
            ).run(),
        ]
        tasks = [asyncio.create_task(service) for service in services]
        try:
            await dispatcher.start_polling(bot, drop_pending_updates=True)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
