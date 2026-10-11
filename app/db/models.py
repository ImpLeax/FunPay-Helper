import datetime
import enum
from typing import Annotated

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

intpk = Annotated[int, mapped_column(primary_key=True)]
created_at = Annotated[
    datetime.datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now()),
]
updated_at = Annotated[
    datetime.datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
]


class Base(DeclarativeBase):
    pass


class AccountStatus(enum.Enum):
    UNLISTED = "not listed"
    SELLING = "For sale"
    SOLD = "sold"


class AccountRegion(enum.Enum):
    UKR = "UKR"
    KAZ = "KAZ"
    USA = "USA"


class SteamAccount(Base):
    __tablename__ = "steam_accounts"

    id: Mapped[intpk]

    steam_login: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Passwords are stored as Fernet tokens, see app.db.crypto.
    steam_password: Mapped[str] = mapped_column(Text, nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_password: Mapped[str] = mapped_column(Text, nullable=False)

    region: Mapped[AccountRegion] = mapped_column(nullable=False)
    status: Mapped[AccountStatus] = mapped_column(default=AccountStatus.UNLISTED, nullable=False)

    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]


class BotSetting(Base):
    """Key/value storage for runtime toggles that must survive restarts."""

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[updated_at]
