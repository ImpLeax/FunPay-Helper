import asyncio
import logging
from collections import defaultdict

from app.db.models import AccountRegion, AccountStatus
from app.db.repository import AccountRepository
from app.funpay import FunPayClient
from app.funpay.models import LotForm

from .lot_secrets import (
    detect_region,
    format_secret_line,
    parse_login,
    plan_status_sync,
    split_secrets,
)
from .runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)

POLL_INTERVAL = 60
IDLE_INTERVAL = 10
DELAY_BETWEEN_SAVES = 2


def apply_secrets(form: LotForm, lines: list[str]) -> None:
    """Write the secret lines into the lot form and enable auto-delivery accordingly."""
    fields = form.fields
    fields["secrets"] = "\n".join(lines)
    fields["amount"] = str(len(lines))
    if lines:
        fields["active"] = "on"
        fields["auto_delivery"] = "on"
    else:
        fields.pop("auto_delivery", None)


class Restocker:
    """Keeps every Steam lot stocked with up to `max_stock` accounts from the database.

    Each cycle it first reconciles DB statuses with the logins currently listed in the lots
    (an account that disappeared from a lot was delivered by FunPay, so it is SOLD), then
    tops up lots that are below `max_stock`.
    """

    def __init__(
        self,
        funpay: FunPayClient,
        accounts: AccountRepository,
        settings: RuntimeSettings,
        subcategory_id: int,
        max_stock: int,
    ) -> None:
        self._funpay = funpay
        self._accounts = accounts
        self._settings = settings
        self._subcategory_id = subcategory_id
        self._max_stock = max_stock

    async def run(self) -> None:
        while True:
            if not self._settings.auto_restock:
                await asyncio.sleep(IDLE_INTERVAL)
                continue
            try:
                await self._restock_once()
            except Exception:
                logger.exception("Restock cycle failed")
            await asyncio.sleep(POLL_INTERVAL)

    async def _restock_once(self) -> None:
        forms: list[tuple[LotForm, AccountRegion]] = []
        failed_regions: set[AccountRegion] = set()

        for lot in await self._funpay.get_my_lots(self._subcategory_id):
            region = detect_region(lot.description)
            if region is None:
                continue
            try:
                forms.append((await self._funpay.get_lot_form(lot.lot_id), region))
            except Exception:
                logger.exception("Failed to load lot %s", lot.lot_id)
                failed_regions.add(region)

        listed: dict[AccountRegion, set[str]] = defaultdict(set)
        for form, region in forms:
            for line in split_secrets(form.fields.get("secrets", "")):
                if login := parse_login(line):
                    listed[region].add(login)

        # Without every lot of a region loaded we cannot tell sold accounts apart.
        for region in {region for _, region in forms} - failed_regions:
            await self._sync_statuses(region, listed[region])

        for form, region in forms:
            try:
                if await self._top_up(form, region):
                    await asyncio.sleep(DELAY_BETWEEN_SAVES)
            except Exception:
                logger.exception("Failed to restock lot %s", form.lot_id)

    async def _sync_statuses(self, region: AccountRegion, listed_logins: set[str]) -> None:
        selling = await self._accounts.get_accounts(region, AccountStatus.SELLING)
        unlisted = await self._accounts.get_accounts(region, AccountStatus.UNLISTED)
        plan = plan_status_sync(
            listed_logins,
            selling={acc.id: acc.steam_login for acc in selling},
            unlisted={acc.id: acc.steam_login for acc in unlisted},
        )
        if plan.sold_ids:
            await self._accounts.set_status(plan.sold_ids, AccountStatus.SOLD)
            logger.info("Marked accounts %s (%s) as sold", plan.sold_ids, region.name)
        if plan.relisted_ids:
            await self._accounts.set_status(plan.relisted_ids, AccountStatus.SELLING)
            logger.warning(
                "Accounts %s (%s) were listed but marked unlisted; fixed",
                plan.relisted_ids,
                region.name,
            )

    async def _top_up(self, form: LotForm, region: AccountRegion) -> bool:
        """Add accounts to the lot if needed. Returns True when the lot was saved."""
        lines = split_secrets(form.fields.get("secrets", ""))
        needed = self._max_stock - len(lines)
        new_accounts = (
            await self._accounts.get_unlisted_credentials(region, needed) if needed > 0 else []
        )
        needs_activation = bool(lines) and "active" not in form.fields
        if not new_accounts and not needs_activation:
            return False

        apply_secrets(form, lines + [format_secret_line(acc) for acc in new_accounts])
        await self._funpay.save_lot_form(form)
        # Marked only after a successful save; _sync_statuses repairs a missed update.
        await self._accounts.set_status([acc.id for acc in new_accounts], AccountStatus.SELLING)
        logger.info(
            "Lot %s (%s) saved with %s new account(s)", form.lot_id, region.name, len(new_accounts)
        )
        return True
