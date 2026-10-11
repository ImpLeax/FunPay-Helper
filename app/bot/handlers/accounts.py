import html
import logging
from dataclasses import asdict

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError

from app.bot.keyboards import AddAccountsCallback, confirm_keyboard
from app.db.models import AccountRegion
from app.db.repository import AccountRepository, NewAccount
from app.services.account_import import parse_account_lines

logger = logging.getLogger(__name__)
router = Router(name="accounts")

MAX_REPORTED_FAILURES = 10
USAGE = (
    "Usage:\n<code>/add_accs REGION\nlogin:password:email:email_password\n...</code>\n"
    f"Regions: {', '.join(r.name for r in AccountRegion)}"
)


class AddAccounts(StatesGroup):
    confirming = State()


async def _delete_quietly(message: Message) -> None:
    """The command contains plaintext passwords, so try to remove it from the chat."""
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.warning("Cannot delete the /add_accs message; is the bot a chat admin?")


@router.message(Command("add_accs"))
async def add_accounts(message: Message, state: FSMContext) -> None:
    header, *lines = (message.text or "").strip().split("\n")
    args = header.split()[1:]
    if not args:
        await message.answer(f"❌ <b>Region not specified.</b>\n{USAGE}")
        return

    region_name = args[0].upper()
    if region_name not in AccountRegion.__members__:
        await message.answer(
            f"❌ <b>Unknown region</b> <code>{html.escape(region_name)}</code>.\n{USAGE}"
        )
        return

    result = parse_account_lines(lines)
    await _delete_quietly(message)
    if not result.accounts:
        await message.answer(f"❌ <b>No valid accounts found.</b>\n{USAGE}")
        return

    await state.set_state(AddAccounts.confirming)
    await state.update_data(
        region=region_name, accounts=[asdict(account) for account in result.accounts]
    )

    text = (
        "❓ <b>Are you sure?</b>\n\n"
        f"About to add <b>{len(result.accounts)}</b> account(s) to the <b>{region_name}</b> region."
    )
    if result.invalid_line_numbers:
        numbers = ", ".join(map(str, result.invalid_line_numbers))
        text += f"\n⚠️ Skipping lines with an invalid format: {numbers}"
    await message.answer(text, reply_markup=confirm_keyboard())


@router.callback_query(AddAccounts.confirming, AddAccountsCallback.filter())
async def confirm_add_accounts(
    call: CallbackQuery,
    callback_data: AddAccountsCallback,
    state: FSMContext,
    accounts: AccountRepository,
) -> None:
    data = await state.get_data()
    await state.clear()
    await call.answer()
    if not isinstance(call.message, Message):
        return

    if not callback_data.confirm:
        await call.message.edit_text("🛑 <b>Cancelled.</b> No accounts were added.")
        return

    region = AccountRegion[data["region"]]
    new_accounts = [NewAccount(**raw) for raw in data["accounts"]]
    await call.message.edit_text(f"🔄 Adding {len(new_accounts)} account(s)...")

    added = 0
    failed: list[str] = []
    for account in new_accounts:
        login = html.escape(account.steam_login)
        try:
            await accounts.add_account(account, region)
            added += 1
        except IntegrityError:
            failed.append(f"<code>{login}</code> (duplicate)")
        except Exception:
            logger.exception("Failed to add an account")
            failed.append(f"<code>{login}</code> (database error)")

    report = f"✅ <b>Added:</b> {added} account(s) to {region.name}."
    if failed:
        report += f"\n\n⚠️ <b>Failed ({len(failed)}):</b>\n" + "\n".join(
            failed[:MAX_REPORTED_FAILURES]
        )
        if len(failed) > MAX_REPORTED_FAILURES:
            report += f"\n<i>...and {len(failed) - MAX_REPORTED_FAILURES} more.</i>"
    await call.message.edit_text(report)
