# 🛡️ VerifyGuard

**A modular Discord verification and anti-bot system built with Python.**

VerifyGuard gives Discord server administrators several ways to verify members before granting access to protected areas of a server.

The project is designed around a shared verification architecture: individual verification methods handle their own user interaction, while common services handle pre-checks, temporary challenges, attempt tracking, rate limiting, role assignment, settings, and logging.

> **Project status:** Beta / portfolio project. VerifyGuard is designed primarily as a single-process Discord bot. Some temporary security state is intentionally kept in memory; see [Current limitations](#-current-limitations).

---

## ✨ Features

### Verification methods

- 🔘 **Button verification** — one-click verification.
- 🔢 **Text CAPTCHA** — generates a temporary code and asks the user to enter it.
- 🖼️ **Image CAPTCHA** — renders a temporary CAPTCHA as an image.
- 📧 **Email verification** — sends a one-time code through SMTP.
- 📱 **Phone verification** — sends a one-time code through Twilio SMS.
- 🔗 **Discord OAuth2** — verifies the Discord identity through an OAuth2 authorization flow.

### Server configuration

- Interactive setup wizard.
- Per-server verification settings stored in SQLite.
- Configurable verified and unverified roles.
- Configurable verification channel.
- Custom welcome message.
- Minimum Discord account-age requirement.
- Maximum failed-attempt setting and temporary lockout.
- Optional kick after the maximum number of failed attempts.
- Enable/disable verification per server.
- Persistent verification buttons that remain registered after bot restarts.
- Settings cache with default merging for newly introduced settings.

### Security and reliability

- Cryptographically secure verification-code generation with Python's `secrets` module.
- Method-specific temporary challenges so one verification method cannot consume another method's challenge.
- Expiring, single-use challenges.
- Account-age and lockout pre-checks.
- Per-user rate limiting for email/SMS sends.
- Global destination rate limiting for email addresses and phone numbers.
- Failed external sends release their rate-limit reservations.
- OAuth2 state tokens are short-lived and bound to the initiating guild/user.
- OAuth2 callback verifies that the returned Discord identity matches the original user.
- Centralized Discord role validation.
- Rejects `@everyone`, managed roles, and roles the bot cannot assign.
- Administrative commands require the Manage Server permission.
- Secrets are supplied through environment variables rather than source code.
- Operational logging uses console output plus a rotating log file.

---

## 🧭 How verification works

A typical flow is:

```text
User joins server
       │
       ▼
Pending / verification state
       │
       ▼
User opens verification message
       │
       ▼
Shared pre-checks
(account age / lockout / enabled)
       │
       ▼
Selected verification method
       │
 ┌─────┼───────────────┐
 ▼     ▼               ▼
CAPTCHA Email/SMS     OAuth2
 │       │              │
 └───────┼──────────────┘
         ▼
   Verification passed
         │
         ▼
    Verified role
         │
         ▼
Unverified role removed
(if configured and possible)
```

The verified role assignment is the primary success condition. If the bot successfully grants the verified role but cannot remove an unverified role, the user remains verified and the cleanup failure is logged for administrators.

---

## 🧩 Architecture

VerifyGuard separates Discord UI/interaction code from reusable verification services and individual verification methods.

```text
                         Discord
                            │
                            ▼
                     Discord Bot Layer
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
          Discord UI     Verification   Setup / Config
          & Commands       Modules
                            │
              ┌─────────────┼─────────────┐
              │       │       │       │    │
              ▼       ▼       ▼       ▼    ▼
            Button  CAPTCHA  Email  Phone OAuth2
              │       │       │       │    │
              └───────┴───────┴───────┴────┘
                            │
                            ▼
                  Shared Core Services
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
       ▼                    ▼                    ▼
  Pre-checks          Challenge / State      Rate limiting
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
                    Verification Service
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
          Role assignment          Audit logging
                 │
                 ▼
              Discord
```

### Directory structure

```text
.
├── assets/
│   └── fonts/
├── core/
│   ├── attempt_tracker.py
│   ├── base.py
│   ├── challenge_store.py
│   ├── discord_oauth.py
│   ├── email_sender.py
│   ├── logging_config.py
│   ├── oauth_state.py
│   ├── prechecks.py
│   ├── rate_limiter.py
│   ├── role_validation.py
│   ├── service.py
│   ├── sms_sender.py
│   └── ui_base.py
├── database/
├── modules/
│   ├── button.py
│   ├── captcha.py
│   ├── email_verification.py
│   ├── image_captcha.py
│   ├── oauth2_verification.py
│   ├── phone_verification.py
│   └── registry.py
├── settings/
│   ├── defaults.py
│   └── manager.py
├── tests/
├── ui/
│   └── setup_wizard.py
├── web/
│   └── server.py
├── bot.py
├── .env.example
├── mypy.ini
├── pyproject.toml
└── pytest.ini
```

### Core components

#### `core/`

Shared behavior used by multiple verification methods:

- `base.py` — common verification-module interface.
- `service.py` — verification success/failure handling, role assignment, attempt reset/recording, and audit logging.
- `challenge_store.py` — temporary method-specific verification challenges.
- `attempt_tracker.py` — failed-attempt counting and temporary lockouts.
- `rate_limiter.py` — atomic in-memory cooldown reservations for external verification sends.
- `prechecks.py` — shared checks such as whether verification is enabled, account age, and lockout state.
- `role_validation.py` — one shared validator for roles selected by administrators.
- `oauth_state.py` — short-lived OAuth2 state storage.
- `discord_oauth.py` — Discord OAuth2 URL creation, token exchange, and identity retrieval.
- `email_sender.py` — SMTP email delivery.
- `sms_sender.py` — Twilio SMS delivery through its HTTP API.
- `logging_config.py` — operational console and rotating-file logging.
- `ui_base.py` — common Discord UI error handling.

#### `modules/`

Each verification method implements the shared `VerificationModule` abstraction. The registry maps a configured method name to its implementation and provides persistent views at startup.

#### `settings/`

`SettingsManager` stores per-guild settings in SQLite, caches them in memory, and merges stored settings with the default configuration. Database/read failures are handled fail-closed so a configuration problem does not silently downgrade a server to an easier verification method.

#### `ui/`

Administrative Discord UI, including the interactive setup wizard.

#### `web/`

The OAuth2 callback HTTP server that runs alongside the Discord bot.

---

## 🛠️ Tech stack

| Technology | Purpose |
| --- | --- |
| Python 3.12+ | Application language |
| discord.py | Discord bot, commands, and UI interactions |
| SQLite | Persistent per-server configuration |
| aiosqlite | Async SQLite access |
| aiohttp | Async HTTP requests and OAuth2 callback server |
| aiosmtplib | SMTP email verification |
| Pillow | Image CAPTCHA generation |
| python-dotenv | Environment configuration |
| Twilio HTTP API | SMS verification |
| pytest + pytest-asyncio | Automated tests |
| mypy | Static type checking |
| Ruff | Linting |

The application does **not** use the `twilio` Python SDK; SMS delivery is performed through Twilio's HTTP API using `aiohttp`.

---

## 🚀 Installation

### Requirements

- Python **3.12 or newer**.
- A Discord application and bot.
- A Discord server where the bot can manage the required roles.
- Git, if cloning the repository.
- SMTP credentials for email verification, if email verification is enabled.
- Twilio credentials for phone verification, if phone verification is enabled.
- A publicly reachable OAuth2 callback URL for OAuth2 verification when deployed outside a local development environment.

### 1. Clone the repository

```bash
git clone https://github.com/TheAliRh/discord-verification-bot.git
cd discord-verification-bot
```

### 2. Create and activate a virtual environment

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install the project

For normal use:

```bash
python -m pip install -e .
```

For development, including testing, mypy, and Ruff:

```bash
python -m pip install -e ".[dev]"
```

### 4. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Then fill in the values you need. See [Configuration](#-configuration).

**Never commit `.env` or any file containing credentials.**

### 5. Run the bot

```bash
python bot.py
```

The application creates its SQLite database under `data/bot.db` automatically. Operational logs are written to `logs/bot.log` when the log directory can be created.

---

## ⚙️ Configuration

The following variables are supported:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `OAUTH_SERVER_PORT` | No | Local HTTP port for the OAuth2 callback server; defaults to `8080` |
| `DISCORD_CLIENT_ID` | OAuth2 | Discord OAuth2 client ID |
| `DISCORD_CLIENT_SECRET` | OAuth2 | Discord OAuth2 client secret |
| `OAUTH_REDIRECT_URI` | OAuth2 | OAuth2 callback URL; defaults to `http://localhost:8080/oauth/callback` |
| `SMTP_HOST` | Email | SMTP server hostname |
| `SMTP_PORT` | Email | SMTP server port; `587` is a common value |
| `SMTP_USERNAME` | Email | SMTP username |
| `SMTP_PASSWORD` | Email | SMTP password |
| `SMTP_FROM_ADDRESS` | Email | Sender address |
| `TWILIO_ACCOUNT_SID` | SMS | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | SMS | Twilio authentication token |
| `TWILIO_FROM_NUMBER` | SMS | Twilio sender phone number |
| `DESTINATION_COOLDOWN_SECONDS` | No | Global cooldown for the same email/phone destination; defaults to `60` |
| `LOG_LEVEL` | No | Operational logging level; defaults to `INFO` |

Only configure the external services used by your selected verification methods.

---

## 🤖 Discord bot setup

Create a Discord application and bot through the Discord Developer Portal.

The bot needs, at minimum, the permissions required for the features you enable. In particular, role-based verification requires:

- **Manage Roles**
- Permission to send messages in the verification channel
- Permission to use the required interaction/UI features

The bot's highest role must be **above every role it needs to assign or remove**.

VerifyGuard validates administrator-selected roles and rejects:

- `@everyone`
- Discord-managed roles
- Roles at or above the bot's highest role
- Roles when the bot lacks **Manage Roles**

For member join handling, enable the **Server Members Intent** in the Discord Developer Portal and keep the corresponding intent enabled in the bot configuration.

---

## 🧑‍💼 Server administration

VerifyGuard exposes administrative commands through Discord slash commands.

### Main commands

| Command | Purpose |
| --- | --- |
| `/verify setup` | Open the interactive setup wizard |
| `/verify-view` | View the current verification configuration |
| `/verify-set-method` | Select the verification method |
| `/verify-set-role` | Set the Verified role |
| `/verify-set-unverified-role` | Set the Unverified role |
| `/verify-set-channel` | Set the verification channel |
| `/verify-set-min-age` | Configure the minimum Discord account age |
| `/verify-toggle` | Enable or disable verification |
| `/verify-post` | Post the verification message in the configured channel |
| `/verify-reset` | Reset server settings to defaults |

These configuration commands require the **Manage Server** permission and only operate inside a Discord server.

### Recommended setup order

1. Run `/verify setup` or configure the settings with the individual commands.
2. Select a valid Verified role.
3. Optionally select an Unverified role.
4. Select the verification channel.
5. Select the verification method.
6. Configure any method-specific external service credentials if needed.
7. Post the verification message with `/verify-post`.

If the configured verification channel no longer exists or cannot be used, `/verify-post` refuses to post instead of silently using another channel.

---

## 🔐 Verification security model

### Temporary challenges

CAPTCHA, email, and phone verification use short-lived challenges stored in memory.

A challenge is scoped by:

```text
(guild_id, user_id, method)
```

This prevents a challenge generated for one verification method from being accepted by another method for the same user.

Challenges expire automatically when checked and are single-use: a submitted challenge is consumed whether the answer succeeds or fails.

### Attempt tracking

Genuine verification failures can count toward the configured maximum number of attempts. Reaching the limit can temporarily lock the user out, and the server may optionally kick the member.

Pre-check failures such as disabled verification or an existing lockout do not consume verification attempts.

### Email and SMS rate limiting

External sends are protected by two independent cooldowns:

1. **Per Discord user + guild** — prevents one account from repeatedly triggering sends.
2. **Per destination** — limits repeated sends to the same email address or phone number across different users and guilds.

The check and reservation happen together in one synchronous operation, preventing two concurrent requests from both passing the same cooldown check. A failed external send releases its reservations.

### OAuth2

OAuth2 uses a short-lived state token tied to the initiating guild and user. After Discord redirects back, the state is consumed and the returned Discord identity is checked against the original user before the Verified role is granted.

---

## 🧪 Testing and development

Run the complete test suite with:

```bash
pytest
```

Run static type checking with:

```bash
mypy .
```

Run Ruff linting with:

```bash
ruff check .
```

The project keeps verification-specific behavior inside `modules/` and shared behavior inside `core/`.

A useful mental model is:

```text
Discord interaction
        ↓
Verification module
        ↓
Shared pre-checks / state / rate limiting
        ↓
Core verification service
        ↓
Discord role + audit logging
```

When adding a new verification method, implement the shared module interface and reuse the existing service/state infrastructure instead of duplicating role-assignment and failure-handling logic.

---

## 📊 Logging

VerifyGuard has two types of logging:

1. **Operational logs** — application startup, errors, warnings, rate-limit events, and other internal events. These are written to the console and, when possible, to a rotating `logs/bot.log` file.
2. **Discord audit logs** — human-readable verification events sent to a configured Discord log channel when one is configured.

Set `LOG_LEVEL=DEBUG` when deeper operational logging is required.

Avoid logging credentials, OAuth tokens, or other sensitive secrets.

---

## ⚠️ Current limitations

VerifyGuard is currently designed primarily as a **single-process application**.

The following temporary state is kept in memory:

- CAPTCHA/email/phone challenges
- Failed-attempt tracking and lockouts
- Email/SMS rate-limit reservations
- OAuth2 state tokens

Therefore, restarting the bot clears this temporary state. Running multiple bot processes that need to share these states would require a shared state mechanism such as Redis or another persistent/distributed store.

The SQLite settings database is persistent, but the current project does not include a database migration framework because the schema is intentionally small.

Email, SMS, and OAuth2 verification depend on external services and their credentials.

---

## 🗺️ Future improvements

Possible future work, depending on real product requirements and scale:

- Persistent/shared temporary verification state.
- More advanced CAPTCHA and accessibility options.
- Verification analytics.
- More administrative configuration controls.
- Stronger external-service timeout/retry handling.
- Reusable HTTP client sessions.
- Graceful shutdown of long-lived resources.
- Production deployment examples.
- CI automation for tests, type checking, and linting.
- Additional verification methods.

These are intentionally future improvements rather than requirements for the current single-process architecture.

---

## 🤝 Contributing

Contributions and improvements are welcome.

When contributing:

1. Keep verification-specific behavior inside the appropriate module.
2. Reuse shared core services where possible.
3. Do not store secrets in source code.
4. Keep changes focused.
5. Add tests for important behavior.
6. Keep documentation and configuration synchronized with the implementation.

---

## 📄 License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

---

## 👤 Author

**TheAliRh**

Built as a modular Discord verification system with a focus on asynchronous Python, extensibility, security-conscious verification flows, and maintainable architecture.
