# AI Side Hustle - Telegram sales and manual verification bot

A Telegram bot for selling and manually verifying payments for the digital PDF guide "AI Side Hustle".

The bot runs on Python 3.11+, aiogram 3, and SQLite with WAL mode enabled. It uses long polling and Telegram file_id caching, keeping server memory and outbound bandwidth low enough to run on free or small hosts (such as Justrunmy.app, Render, Railway, or a basic VPS).

---

## Features

- **Language separation**: The customer checkout flow is in English. The owner review interface is in Persian (Farsi). Developer logs and notifications are in English.
- **Telegram file_id caching**: The PDF (`assets/AI_Side_Hustle.pdf`) is uploaded to Telegram once. Subsequent purchases are delivered using the cached `file_id`, so delivery uses almost zero server bandwidth and memory.
- **Two-step verification flow**: Buyers enter their TON transaction hash first, then upload a screenshot receipt. The bot tells buyers to save both before they make their payment.
- **Duplicate transaction checks**: The database enforces unique transaction hashes to prevent replaying old transactions.
- **Admin verification**: The owner receives order details with the screenshot attached, then approves or rejects the order with inline buttons. Multiple clicks on review buttons do not trigger duplicate file sends.
- **Preset rejection reasons**: The owner can select preset rejection reasons in Persian, which are translated into English when sent to the buyer. Custom rejection notes are also supported.
- **Identity privacy**: The bot never exposes admin or developer user IDs or usernames to buyers.
- **Configurable pricing and expiry**: Prices in USD and TON, along with the 120-minute order timeout, are configured in `.env`.

---

## Project structure

```text
ai_hustle_tg_bot/
├── assets/
│   └── AI_Side_Hustle.pdf         # PDF file delivered to buyers
├── data/                          # SQLite database directory (mounted in Docker)
├── src/
│   ├── config.py                  # Environment settings validation (Pydantic)
│   ├── database/
│   │   ├── models.py              # Order and BotCache SQLAlchemy models
│   │   └── session.py             # Async SQLite engine with WAL mode
│   ├── services/
│   │   ├── order_service.py       # Order lifecycle, state transitions, expiry checks
│   │   ├── delivery_service.py    # Telegram file delivery and file_id caching
│   │   └── notification_service.py# Buyer, owner, and developer message dispatchers
│   ├── bot/
│   │   ├── dispatcher.py          # aiogram dispatcher and router setup
│   │   ├── states.py              # FSM states for checkout and admin review
│   │   ├── middlewares/
│   │   │   ├── auth_middleware.py # Owner ID authorization check
│   │   │   └── db_middleware.py   # Async session injection per update
│   │   ├── keyboards/
│   │   │   ├── buyer_keyboards.py # English inline keyboards for buyers
│   │   │   └── owner_keyboards.py # Persian inline keyboards for owner
│   │   └── handlers/
│   │       ├── buyer_handlers.py  # /start, checkout, hash and receipt submission
│   │       ├── owner_handlers.py  # Review, approval, presets, custom rejection
│   │       └── common_handlers.py # Unknown message and error fallbacks
│   ├── utils/
│   │   ├── code_generator.py      # Random order number generator (ASH-XXXXX)
│   │   └── logger.py              # Application logger
│   └── main.py                    # Entry point and long polling loop
├── tests/                         # Test suite (19 test cases)
├── .env.example                   # Environment variable template
├── Dockerfile                     # Multi-stage Docker build
└── docker-compose.yml             # Docker compose configuration
```

---

## Configuration

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Telegram bot token from @BotFather | `123456789:ABCdefGhI...` |
| `OWNER_ID` | Numeric Telegram user ID of the owner (@MoHo72) | `72101760` |
| `DEVELOPER_ID` | Numeric Telegram user ID of the developer (@mehdi_kh_278) | `347382968` |
| `TON_WALLET_ADDRESS` | Receiving TON wallet address | `EQD...` |
| `PRICE_USD` | Launch discount price in USD | `79.0` |
| `ORIGINAL_PRICE_USD` | Regular price in USD | `100.0` |
| `PRICE_TON` | Equivalent price in TON | `12.5` |
| `ORDER_TIMEOUT_MINUTES` | Minutes before an unpaid order expires | `120` |
| `PDF_FILE_PATH` | Path to the PDF product file | `./assets/AI_Side_Hustle.pdf` |
| `DATABASE_URL` | Async SQLite connection string | `sqlite+aiosqlite:///./data/bot.db` |

---

## How to run

### Local Python setup

1. Clone the repository:
   ```bash
   git clone https://github.com/meytiii/ai_hustle_tg_bot.git
   cd ai_hustle_tg_bot
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   # Windows (PowerShell):
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. Set up `.env`:
   ```bash
   cp .env.example .env
   # Edit .env with your BOT_TOKEN and TON_WALLET_ADDRESS
   ```

4. Place your PDF at `assets/AI_Side_Hustle.pdf`.

5. Run the bot:
   ```bash
   python -m src.main
   ```

---

### Docker and Docker Compose

1. Fill in your secrets in `.env`.
2. Build and start the container:
   ```bash
   docker compose up -d --build
   ```
3. View logs:
   ```bash
   docker compose logs -f
   ```
4. Stop the container:
   ```bash
   docker compose down
   ```

---

### Free hosting (Render, Railway, Justrunmy.app)

The bot uses long polling, so it does not need a public domain, open ports, or an SSL certificate.

1. Mount a persistent disk to `/app/data` so the SQLite database file persists across restarts.
2. Add the environment variables from `.env.example` in your host's dashboard.
3. Set the start command to:
   ```bash
   python -m src.main
   ```

---

## Running tests

Run the test suite with pytest:

```bash
pytest -v tests/
```

The 19 tests cover:
- Pydantic configuration validation
- Order state transitions (creation, receipt upload, review, approval, rejection, cancellation, timeout)
- Duplicate transaction hash rejection
- Owner authorization middleware
- Delivery caching logic
- Notification formatting in English and Persian
- End-to-end checkout and review flows

---

## Order workflow

```text
Buyer                                   Owner (Persian)                     Developer (English)
  │                                           │                                     │
/start                                        │                                     │
  │                                           │                                     │
Buy Now                                       │                                     │
  │ (instructions + wallet address)           │                                     │
Sends TON                                     │                                     │
  │                                           │                                     │
Submits TX hash and screenshot                │                                     │
  ├──────────────────────────────────────────→│                                     │
  │ (status: UNDER_REVIEW)           Checks wallet and proof                        │
  │                                           │                                     │
  │                                    Approve or Reject                            │
  │                                           │                                     │
  │←── Delivered PDF (if approved) ───────────┴────────────────────────────────────→│
  │←── Rejection reason (if rejected)                                    Sales report
```

---

## Security notes

- **SQLite WAL mode**: Provides safe concurrent reads and writes without database lock contention.
- **Idempotency**: Approval and rejection checks require the order to be in `UNDER_REVIEW`. Repeated clicks do not resend files or alter order status.
- **Replay prevention**: Unique constraints on `tx_hash` reject duplicate transaction submissions.
- **Safe errors**: Internal exceptions trigger technical alerts to the developer while showing friendly error messages to users.
