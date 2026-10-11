# FunPay TG Bot

A Telegram bot that automates selling Steam accounts on [FunPay](https://funpay.com). It runs in a private Telegram group and handles the routine work of a seller:

- **Chat forwarding.** New buyer messages from FunPay chats are posted to the group with a link to the conversation.
- **Review requests.** Buyers of new paid Steam orders get a polite message asking them to confirm the order and leave a review.
- **Automatic restocking.** Steam lots are kept filled with up to N accounts from a PostgreSQL stock. FunPay auto-delivery hands them to buyers, and the bot detects delivered accounts and marks them as sold.
- **Stock management from Telegram.** Commands import accounts in bulk, show stock per region and status, check the FunPay balance, and toggle the services.

## Tech stack

Python 3.12 · [aiogram 3](https://docs.aiogram.dev) · aiohttp · SQLAlchemy 2 (async) + asyncpg · PostgreSQL · BeautifulSoup/lxml · pydantic-settings · cryptography (Fernet) · uv · Docker Compose · pytest · ruff

## Architecture

```
app/
├── __main__.py      entrypoint: wiring, background tasks, graceful shutdown
├── config.py        typed settings from environment / .env
├── funpay/          minimal async FunPay web client (aiohttp + HTML parsing)
├── db/              SQLAlchemy models, repositories, password encryption
├── services/        long-running loops: chat notifier, review requester, restocker
└── bot/             aiogram routers, filters, keyboards and message texts
```

- FunPay has no public API. `app/funpay` drives the website with the account's `golden_key` cookie. Parsing is isolated in pure functions (`parsers.py`) so it can be tested against HTML fixtures. The session is refreshed periodically and again on demand whenever FunPay reports it as expired.
- Background services run as asyncio tasks next to aiogram polling. The auto-restock and auto-reply toggles are stored in the database, so they survive restarts.
- Dependencies reach handlers through aiogram's workflow data, so there are no module-level globals.

## Getting started

### 1. Configure

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `CHAT_ID` | ID of the group the bot serves (send `/chatid` to the bot to get it) |
| `THREAD_ID` | Optional forum topic for buyer message notifications |
| `GOLDEN_KEY` | `golden_key` cookie from a browser session logged in to FunPay |
| `POSTGRES_*` | Database credentials and location |
| `ENCRYPTION_KEY` | Fernet key used to encrypt stored passwords (see `.env.example` for how to generate it) |
| `STEAM_SUBCATEGORY_ID`, `MAX_LOT_STOCK` | Optional: FunPay subcategory to manage (default `89`) and accounts kept per lot (default `3`) |

### 2a. Run with Docker

```bash
docker compose up -d --build
```

### 2b. Run locally

```bash
uv sync
docker compose up -d db
uv run python -m app
```

The bot must be an admin of the group so it can delete `/add_accs` messages, which contain plaintext passwords.

## Bot commands

| Command | Description |
| --- | --- |
| `/start` | Overview of features and commands |
| `/stats` | FunPay balance, active orders and unlisted stock |
| `/stock` | Stock per region and status |
| `/add_accs REGION` | Import accounts: one `login:password:email:email_password` per line after the command |
| `/settings` | Toggle auto-restock and auto-reply |
| `/chatid` | Show the current chat and topic IDs (works in any chat) |

The restocker picks a region for each lot by looking for a keyword in the lot description: `Украина`, `Казахстан` or `США`.

## Example of work
<img width="280" height="136" alt="photo_2026-10-11_19-16-31" src="https://github.com/user-attachments/assets/66ed462c-241b-453b-bac5-6f3dc2577115" />

<img width="314" height="210" alt="photo_2026-10-11_19-16-35" src="https://github.com/user-attachments/assets/f351f6ec-5204-4ea8-aadb-e9c50faac133" />

## Security

- All secrets come from environment variables. `.env` is git-ignored, and `SecretStr` keeps them out of logs and reprs.
- Steam and email passwords are encrypted at rest with Fernet. They are decrypted only when an account is added to a lot.
- The bot answers only in the configured chat, for both messages and button callbacks.
- Buyer-supplied text is HTML-escaped before it is sent to Telegram.
- In Docker Compose, PostgreSQL is bound to `127.0.0.1` only.

If you are upgrading a database created by an older version that stored plaintext passwords, run this once (it is safe to repeat):

```bash
uv run python -m scripts.encrypt_existing_accounts
```

## Development

```bash
uv sync                    # install runtime + dev dependencies
uv run pytest              # run tests
uv run ruff check .        # lint
uv run ruff format .       # format
```
