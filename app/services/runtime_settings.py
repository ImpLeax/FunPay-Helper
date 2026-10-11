from app.db.repository import SettingsRepository

AUTO_RESTOCK_KEY = "auto_restock_enabled"
AUTO_REPLY_KEY = "auto_reply_enabled"


class RuntimeSettings:
    """Feature toggles controlled from Telegram, cached in memory and persisted to the DB."""

    def __init__(self, repository: SettingsRepository) -> None:
        self._repository = repository
        self.auto_restock = False
        self.auto_reply = False

    async def load(self) -> None:
        stored = await self._repository.get_all()
        self.auto_restock = stored.get(AUTO_RESTOCK_KEY) == "1"
        self.auto_reply = stored.get(AUTO_REPLY_KEY) == "1"

    async def toggle_auto_restock(self) -> bool:
        self.auto_restock = not self.auto_restock
        await self._repository.set(AUTO_RESTOCK_KEY, "1" if self.auto_restock else "0")
        return self.auto_restock

    async def toggle_auto_reply(self) -> bool:
        self.auto_reply = not self.auto_reply
        await self._repository.set(AUTO_REPLY_KEY, "1" if self.auto_reply else "0")
        return self.auto_reply
