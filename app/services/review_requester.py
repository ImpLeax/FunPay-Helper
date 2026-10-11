import asyncio
import logging
from collections import OrderedDict

from app.funpay import FunPayClient
from app.funpay.models import Order

from .runtime_settings import RuntimeSettings

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30
IDLE_INTERVAL = 10
ERROR_BACKOFF = 60
MAX_REMEMBERED_ORDERS = 2000

# Sent to Russian-speaking FunPay buyers, hence not in English.
REVIEW_REQUEST_TEXT = (
    "Здравствуйте, ещё раз спасибо за покупку! Если всё в порядке, пожалуйста, "
    "подтвердите заказ и оставьте отзыв — буду очень благодарен."
)


class ReviewRequester:
    """Asks buyers of new paid Steam orders to confirm the order and leave a review."""

    def __init__(
        self, funpay: FunPayClient, settings: RuntimeSettings, steam_subcategory_id: int
    ) -> None:
        self._funpay = funpay
        self._settings = settings
        self._subcategory_id = steam_subcategory_id
        self._handled: OrderedDict[str, None] = OrderedDict()
        self._was_enabled = False

    async def run(self) -> None:
        while True:
            if not self._settings.auto_reply:
                self._was_enabled = False
                await asyncio.sleep(IDLE_INTERVAL)
                continue
            try:
                await self._poll_once()
                await asyncio.sleep(POLL_INTERVAL)
            except Exception:
                logger.exception("Review request polling failed")
                await asyncio.sleep(ERROR_BACKOFF)

    async def _poll_once(self) -> None:
        orders = await self._funpay.get_paid_sales()

        # Orders that were already paid when the feature got enabled are not messaged.
        if not self._was_enabled:
            for order in orders:
                self._remember(order.order_id)
            self._was_enabled = True
            return

        for order in orders:
            if order.order_id in self._handled:
                continue
            if self._is_target(order):
                try:
                    await self._funpay.send_message(order.chat_id, REVIEW_REQUEST_TEXT)
                    logger.info("Sent review request for order %s", order.order_id)
                except Exception:
                    logger.exception("Failed to send review request for order %s", order.order_id)
            self._remember(order.order_id)

    def _is_target(self, order: Order) -> bool:
        return order.subcategory_id == self._subcategory_id or "Steam" in order.subcategory_name

    def _remember(self, order_id: str) -> None:
        self._handled[order_id] = None
        while len(self._handled) > MAX_REMEMBERED_ORDERS:
            self._handled.popitem(last=False)
