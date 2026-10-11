import html

from app.db.models import AccountRegion, AccountStatus
from app.funpay.models import AccountInfo
from app.services.runtime_settings import RuntimeSettings

START_TEXT = (
    "🤖 <b>FunPay Helper Bot</b>\n"
    "Automates Steam account sales on FunPay.\n\n"
    "<b>Background services:</b>\n"
    "💬 Forwards new buyer messages to this chat.\n"
    "⭐ Asks buyers of new orders to confirm and leave a review.\n"
    "🔄 Keeps FunPay lots stocked with accounts from the database "
    "(FunPay auto-delivery hands them to buyers).\n\n"
    "<b>Commands:</b>\n"
    "📊 /stats — FunPay balance, active orders and stock\n"
    "🗄 /stock — detailed stock per region and status\n"
    "➕ /add_accs REGION — import accounts, one "
    "<code>login:password:email:email_password</code> per line\n"
    "⚙️ /settings — turn auto-restock and auto-reply on or off\n"
    "🆔 /chatid — show the current chat and thread IDs"
)

STATUS_LABELS = {
    AccountStatus.UNLISTED: "Not listed",
    AccountStatus.SELLING: "For sale",
    AccountStatus.SOLD: "Sold",
}


def _on_off(enabled: bool) -> str:
    return "🟢 <b>ON</b>" if enabled else "🔴 <b>OFF</b>"


def settings_text(settings: RuntimeSettings) -> str:
    return (
        "⚙️ <b>Bot Settings</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔄 <b>Auto-Restock:</b> {_on_off(settings.auto_restock)}\n"
        f"💬 <b>Auto-Reply:</b> {_on_off(settings.auto_reply)}\n"
    )


def stats_text(account: AccountInfo, stock: dict[AccountRegion, dict[AccountStatus, int]]) -> str:
    regions = list(stock)
    stock_lines = "\n".join(
        f"{'└' if i == len(regions) - 1 else '├'} {region.name}: "
        f"<b>{stock[region][AccountStatus.UNLISTED]} pcs.</b>"
        for i, region in enumerate(regions)
    )
    return (
        f"📊 <b>Account:</b> <code>{html.escape(account.username)}</code> "
        f"(ID: {account.user_id})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Finance and orders</b>\n"
        f"├ Balance: <b>{account.balance:g} {html.escape(account.currency)}</b>\n"
        f"├ Active sales: <b>{account.active_sales}</b>\n"
        f"└ Active purchases: <b>{account.active_purchases}</b>\n\n"
        "📦 <b>Unlisted accounts in stock</b>\n"
        f"{stock_lines}"
    )


def stock_text(stock: dict[AccountRegion, dict[AccountStatus, int]]) -> str:
    parts = ["📦 <b>Current Stock Overview</b>\n"]
    for region, statuses in stock.items():
        parts.append(f"🌍 <b>{region.name}</b> (total: {sum(statuses.values())})")
        items = list(statuses.items())
        for i, (status, count) in enumerate(items):
            branch = "└" if i == len(items) - 1 else "├"
            parts.append(f"{branch} {STATUS_LABELS[status]}: <b>{count}</b>")
        parts.append("")
    return "\n".join(parts)


def error_text(title: str, error: Exception) -> str:
    return f"❌ <b>{title}</b>\n<code>{html.escape(str(error))}</code>"
