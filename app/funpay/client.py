"""Minimal asynchronous FunPay web client covering the operations this bot needs."""

import asyncio
import json
import logging
import secrets
import string
from collections.abc import Awaitable, Callable
from typing import Any, Self

import aiohttp
from yarl import URL

from . import parsers
from .errors import LotSaveError, MessageNotSentError, RequestError, UnauthorizedError
from .models import AccountInfo, ChatMessage, ChatPreview, LotForm, MyLot, Order

logger = logging.getLogger(__name__)

BASE_URL = URL("https://funpay.com/")
MAX_ATTEMPTS = 5
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
XHR_HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
}


class _TransientError(RequestError):
    """Rate limit or server-side failure worth retrying."""


def _random_tag() -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


class FunPayClient:
    """Authenticates with the `golden_key` cookie and talks to FunPay's web endpoints."""

    def __init__(self, golden_key: str, user_agent: str) -> None:
        self._golden_key = golden_key
        self._user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None
        self._refresh_lock = asyncio.Lock()
        self.account: AccountInfo | None = None

    async def __aenter__(self) -> Self:
        jar = aiohttp.CookieJar()
        jar.update_cookies({"golden_key": self._golden_key, "cookie_prefs": "1"}, BASE_URL)
        self._session = aiohttp.ClientSession(
            base_url=BASE_URL,
            cookie_jar=jar,
            headers={"user-agent": self._user_agent},
            timeout=REQUEST_TIMEOUT,
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def user_id(self) -> int:
        return self._require_account().user_id

    def _require_account(self) -> AccountInfo:
        if self.account is None:
            raise RuntimeError("FunPayClient.refresh() must be called first")
        return self.account

    # ---------------------------------------------------------------- transport

    async def _request(self, method: str, path: str, **kwargs: Any) -> str:
        """Send a request with retries on rate limits and transient server errors."""
        if self._session is None:
            raise RuntimeError("FunPayClient must be used as an async context manager")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with self._session.request(method, path, **kwargs) as response:
                    if response.url.path.rstrip("/").endswith("account/login"):
                        raise UnauthorizedError("Redirected to the login page")
                    if response.status in (401, 403):
                        raise UnauthorizedError(f"FunPay responded with {response.status}")
                    if response.status == 429 or response.status >= 500:
                        raise _TransientError(f"FunPay responded with {response.status}")
                    if response.status != 200:
                        raise RequestError(f"{method} {path} failed with {response.status}")
                    return await response.text()
            except (_TransientError, aiohttp.ClientError, TimeoutError) as e:
                if attempt == MAX_ATTEMPTS:
                    raise
                delay = min(2**attempt, 30)
                logger.warning("%s %s: %s; retrying in %ss", method, path, e, delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _with_reauth[T](self, call: Callable[[], Awaitable[T]]) -> T:
        """Run `call`, refreshing the session once if FunPay reports it as expired."""
        try:
            return await call()
        except UnauthorizedError:
            logger.info("FunPay session expired, refreshing")
            await self.refresh()
            return await call()

    async def _runner(self, objects: list[dict], request: dict | None = None) -> dict:
        payload = {
            "objects": json.dumps(objects),
            "request": json.dumps(request) if request else "false",
            "csrf_token": self._require_account().csrf_token,
        }
        text = await self._request("POST", "runner/", data=payload, headers=XHR_HEADERS)
        return json.loads(text)

    # ---------------------------------------------------------------- account

    async def refresh(self) -> AccountInfo:
        """Load account info, CSRF token and a fresh PHPSESSID. Call periodically."""
        async with self._refresh_lock:
            account = parsers.parse_account_info(await self._request("GET", ""))
            try:
                balance = parsers.parse_balance(await self._request("GET", "account/balance"))
            except (RequestError, ValueError) as e:
                logger.warning("Could not read balance: %s", e)
                balance = None
            if balance:
                account.balance, account.currency = balance
            self.account = account
            return account

    # ---------------------------------------------------------------- chats

    async def get_chats(self) -> list[ChatPreview]:
        async def call() -> list[ChatPreview]:
            response = await self._runner(
                [
                    {
                        "type": "chat_bookmarks",
                        "id": self.user_id,
                        "tag": _random_tag(),
                        "data": False,
                    }
                ]
            )
            bookmarks = parsers.find_runner_object(response.get("objects", []), "chat_bookmarks")
            html = (bookmarks or {}).get("data", {}).get("html", "")
            return parsers.parse_chat_previews(html) if html else []

        return await self._with_reauth(call)

    @staticmethod
    def _chat_node(chat_id: int | str) -> dict:
        return {
            "type": "chat_node",
            "id": chat_id,
            "tag": "00000000",
            "data": {"node": chat_id, "last_message": -1, "content": ""},
        }

    async def get_chat_messages(self, chat_id: int | str) -> list[ChatMessage]:
        async def call() -> list[ChatMessage]:
            response = await self._runner([self._chat_node(chat_id)])
            node = parsers.find_runner_object(response.get("objects", []), "chat_node")
            return parsers.parse_chat_messages(node) if node else []

        return await self._with_reauth(call)

    async def send_message(self, chat_id: int | str, text: str) -> None:
        request = {
            "action": "chat_message",
            "data": {"node": chat_id, "last_message": -1, "content": text},
        }

        async def call() -> dict:
            return await self._runner([self._chat_node(chat_id)], request)

        result = (await self._with_reauth(call)).get("response")
        if not result:
            raise MessageNotSentError(f"No response when sending a message to chat {chat_id}")
        if error := result.get("error"):
            raise MessageNotSentError(f"Chat {chat_id}: {error}")

    # ---------------------------------------------------------------- orders

    async def get_paid_sales(self) -> list[Order]:
        async def call() -> list[Order]:
            html = await self._request("GET", "orders/trade", params={"state": "paid"})
            return parsers.parse_orders(html, self.user_id)

        return await self._with_reauth(call)

    # ---------------------------------------------------------------- lots

    async def get_my_lots(self, subcategory_id: int) -> list[MyLot]:
        async def call() -> list[MyLot]:
            return parsers.parse_my_lots(await self._request("GET", f"lots/{subcategory_id}/trade"))

        return await self._with_reauth(call)

    async def get_lot_form(self, lot_id: int) -> LotForm:
        async def call() -> LotForm:
            html = await self._request("GET", "lots/offerEdit", params={"offer": lot_id})
            if token := parsers.parse_csrf_token(html):
                self._require_account().csrf_token = token
            return parsers.parse_lot_form(html, lot_id)

        return await self._with_reauth(call)

    async def save_lot_form(self, form: LotForm) -> None:
        async def call() -> dict:
            data = {**form.fields, "csrf_token": self._require_account().csrf_token}
            text = await self._request("POST", "lots/offerSave", data=data, headers=XHR_HEADERS)
            return json.loads(text)

        result = await self._with_reauth(call)
        if result.get("error") or result.get("errors"):
            details = result.get("errors") or result.get("error")
            raise LotSaveError(f"Lot {form.lot_id} was not saved: {details}")
