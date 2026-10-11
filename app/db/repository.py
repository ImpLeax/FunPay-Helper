from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import URL, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .crypto import PasswordCipher
from .models import AccountRegion, AccountStatus, Base, BotSetting, SteamAccount


@dataclass(slots=True, frozen=True)
class AccountCredentials:
    """Decrypted account data, ready to be delivered to a buyer."""

    id: int
    steam_login: str
    steam_password: str
    email: str
    email_password: str


@dataclass(slots=True, frozen=True)
class NewAccount:
    steam_login: str
    steam_password: str
    email: str
    email_password: str


def create_engine(url: URL) -> AsyncEngine:
    return create_async_engine(url, echo=False, pool_pre_ping=True)


async def init_models(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class AccountRepository:
    def __init__(self, session_factory: async_sessionmaker, cipher: PasswordCipher) -> None:
        self._session_factory = session_factory
        self._cipher = cipher

    async def add_account(self, account: NewAccount, region: AccountRegion) -> None:
        """Insert an account. Raises sqlalchemy.exc.IntegrityError for duplicate logins."""
        async with self._session_factory() as session:
            session.add(
                SteamAccount(
                    steam_login=account.steam_login,
                    steam_password=self._cipher.encrypt(account.steam_password),
                    email=account.email,
                    email_password=self._cipher.encrypt(account.email_password),
                    region=region,
                )
            )
            await session.commit()

    async def get_accounts(
        self, region: AccountRegion, status: AccountStatus
    ) -> list[SteamAccount]:
        """Return accounts without decrypting their passwords."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(SteamAccount).where(
                    SteamAccount.region == region, SteamAccount.status == status
                )
            )
            return list(result.scalars().all())

    async def get_unlisted_credentials(
        self, region: AccountRegion, limit: int
    ) -> list[AccountCredentials]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SteamAccount)
                .where(
                    SteamAccount.status == AccountStatus.UNLISTED,
                    SteamAccount.region == region,
                )
                .order_by(SteamAccount.id)
                .limit(limit)
            )
            return [
                AccountCredentials(
                    id=acc.id,
                    steam_login=acc.steam_login,
                    steam_password=self._cipher.decrypt(acc.steam_password),
                    email=acc.email,
                    email_password=self._cipher.decrypt(acc.email_password),
                )
                for acc in result.scalars()
            ]

    async def set_status(self, account_ids: Iterable[int], status: AccountStatus) -> int:
        ids = list(account_ids)
        if not ids:
            return 0
        async with self._session_factory() as session:
            result = await session.execute(
                update(SteamAccount).where(SteamAccount.id.in_(ids)).values(status=status)
            )
            await session.commit()
            return result.rowcount

    async def get_stock_stats(self) -> dict[AccountRegion, dict[AccountStatus, int]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    SteamAccount.region, SteamAccount.status, func.count(SteamAccount.id)
                ).group_by(SteamAccount.region, SteamAccount.status)
            )
            stats = {region: dict.fromkeys(AccountStatus, 0) for region in AccountRegion}
            for region, status, count in result:
                stats[region][status] = count
            return stats


class SettingsRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def get_all(self) -> dict[str, str]:
        async with self._session_factory() as session:
            result = await session.execute(select(BotSetting.key, BotSetting.value))
            return {key: value for key, value in result}

    async def set(self, key: str, value: str) -> None:
        async with self._session_factory() as session:
            stmt = insert(BotSetting).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(
                index_elements=[BotSetting.key],
                set_={"value": stmt.excluded.value, "updated_at": func.now()},
            )
            await session.execute(stmt)
            await session.commit()
