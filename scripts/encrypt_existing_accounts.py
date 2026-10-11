"""One-off migration: encrypt plaintext passwords stored by older versions of the bot.

Safe to run repeatedly: values that already decrypt with ENCRYPTION_KEY are left untouched.

    uv run python -m scripts.encrypt_existing_accounts
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.db.crypto import PasswordCipher
from app.db.models import SteamAccount
from app.db.repository import create_engine


async def main() -> None:
    settings = get_settings()
    cipher = PasswordCipher(settings.encryption_key.get_secret_value())
    engine = create_engine(settings.database_url)

    async with engine.begin() as conn:
        # Fernet tokens can exceed the old VARCHAR(255) limit.
        for column in ("steam_password", "email_password"):
            await conn.execute(text(f"ALTER TABLE steam_accounts ALTER COLUMN {column} TYPE TEXT"))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    encrypted = 0
    async with session_factory() as session:
        for account in (await session.execute(select(SteamAccount))).scalars():
            changed = False
            for attr in ("steam_password", "email_password"):
                value = getattr(account, attr)
                if not cipher.is_encrypted(value):
                    setattr(account, attr, cipher.encrypt(value))
                    changed = True
            encrypted += changed
        await session.commit()

    await engine.dispose()
    print(f"Encrypted passwords of {encrypted} account(s).")


if __name__ == "__main__":
    asyncio.run(main())
