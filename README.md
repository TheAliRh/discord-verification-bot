# 🛡️ VerifyGuard

**A modular Discord verification and anti-bot system built with Python.**

VerifyGuard gives Discord server administrators multiple ways to verify members before granting them access to protected areas of a server.

The project is designed around a modular verification architecture, allowing different verification methods to share common verification, role-assignment, logging, and configuration logic.

---

## ✨ Features

### Verification Methods

* 🔘 **Button verification** — Simple one-click verification
* 🔢 **Text CAPTCHA** — Users solve a generated CAPTCHA challenge
* 🖼️ **Image CAPTCHA** — CAPTCHA rendered as an image
* 📧 **Email verification** — Verification through a one-time email code
* 📱 **Phone verification** — Verification through an SMS code
* 🔗 **Discord OAuth2** — Verify through Discord's OAuth2 authorization flow

### Server Configuration

* Interactive setup wizard
* Per-server verification settings
* Configurable verification role
* Configurable verification channel
* Custom welcome message
* Minimum Discord account-age requirement
* Persistent verification buttons
* Settings stored in SQLite
* Automatic merging of stored settings with default configuration

### Security & Reliability

* Verification sessions with expiration
* Single-use OAuth2 state tokens
* OAuth2 identity verification
* Account-age prechecks
* Discord role hierarchy validation
* Permission checks for administrative commands
* Environment-based secret management
* Shared verification service for consistent role assignment and logging

---

## 📸 How It Works

A typical verification flow looks like this:

```text
                    User joins server
                           │
                           ▼
                 Verification message
                           │
                           ▼
                   User clicks Verify
                           │
                           ▼
                  Shared pre-checks
                           │
                           ▼
                Selected verification
                       method
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       CAPTCHA          Email/SMS        OAuth2
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    Verification passed
                           │
                           ▼
                  Verified role assigned
```

The verification method is selected per server, while the final verification process is handled by shared core services.

---

## 🧩 Architecture

VerifyGuard separates Discord-specific interactions from the core verification logic.

```text
                         Discord
                            │
                            ▼
                     Discord Bot Layer
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
          UI / Views    Verification   Setup / Config
                           Modules
              │             │
              │      ┌──────┼──────┐
              │      │      │      │
              │    Button CAPTCHA OAuth2
              │      │      │      │
              │      └──────┼──────┘
              │             │
              └─────────────┤
                            ▼
                  Verification Service
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
          Role Assignment             Logging
                │
                ▼
             Discord
```

### Core Components

#### `core/`

Contains functionality shared across verification methods.

* `base.py` — Defines the common `VerificationModule` interface
* `service.py` — Handles successful/failed verification, role assignment, and logging
* `challenge_store.py` — Stores and validates temporary verification challenges
* `oauth_state.py` — Creates and consumes short-lived OAuth2 state tokens
* `discord_oauth.py` — Handles Discord OAuth2 authorization and API requests
* `email_sender.py` — Sends verification emails through SMTP
* `sms_sender.py` — Sends verification SMS messages
* `prechecks.py` — Handles shared verification requirements such as account age

#### `modules/`

Contains individual verification implementations.

Each verification method implements the shared `VerificationModule` interface.

```text
modules/
├── button.py
├── captcha.py
├── image_captcha.py
├── email_verification.py
├── phone_verification.py
└── oauth2_verification.py
```

This allows new verification methods to be added without rewriting the core verification flow.

#### `settings/`

Handles persistent, per-server configuration.

Settings are stored in SQLite and cached in memory to avoid unnecessary database queries during verification interactions.

#### `ui/`

Contains Discord UI components used for administrative configuration.

The setup wizard allows server administrators to configure verification interactively rather than manually editing configuration files.

#### `web/`

Contains the HTTP server used by the OAuth2 verification flow.

The web server runs alongside the Discord bot and exposes the OAuth2 callback endpoint.

---

## ⚙️ Tech Stack

| Technology    | Purpose                                        |
| ------------- | ---------------------------------------------- |
| Python        | Application language                           |
| discord.py    | Discord bot and interaction framework          |
| SQLite        | Persistent server configuration                |
| aiosqlite     | Async SQLite access                            |
| aiohttp       | Async HTTP requests and OAuth2 callback server |
| aiosmtplib    | Email verification                             |
| Pillow        | Image CAPTCHA generation                       |
| python-dotenv | Environment variable management                |
| Twilio API    | SMS verification                               |

---

## 🚀 Installation

### Requirements

* Python 3.12+
* A Discord application and bot
* A Discord server where you can manage roles
* Git

Additional services are required if you want to use email, SMS, or OAuth2 verification.

---

### 1. Clone the repository

```bash
git clone https://github.com/TheAliRh/discord-verification-bot.git
cd discord-verification-bot
```

### 2. Create a virtual environment

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

Install the project's Python dependencies before starting the bot.

> Dependency configuration is currently being formalized. See the repository configuration for the exact packages required by the current version.

### 4. Configure environment variables

Create a `.env` file in the project root.

```env
DISCORD_TOKEN=your_discord_bot_token

# OAuth2
OAUTH_SERVER_PORT=8080
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
OAUTH_REDIRECT_URI=

# Email verification
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_ADDRESS=

# SMS verification
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

Only configure the services you intend to use.

**Never commit `.env` or any file containing secrets to the repository.**

---

## 🤖 Discord Bot Setup

Create an application through the Discord Developer Portal and create a bot for the application.

The bot requires the appropriate permissions to:

* Manage roles
* Send messages
* Embed links
* Use slash commands
* Send messages in the configured verification channel

The bot's highest role must be **above the role it needs to assign**.

For member-related functionality, the required Discord intents must also be enabled for the bot.

---

## ▶️ Running the Bot

Once the environment has been configured:

```bash
python bot.py
```

The bot will:

1. Start the OAuth2 callback server
2. Initialize the SQLite settings database
3. Register persistent verification views
4. Synchronize Discord slash commands
5. Connect to Discord

---

## 🛠️ Server Configuration

VerifyGuard provides an interactive setup wizard.

### `/verify setup`

Opens the configuration interface where administrators can select:

* Verification method
* Verified role
* Verification channel
* Welcome message

After saving the configuration, use:

```text
/verify-post
```

to publish the verification message.

### Available Commands

| Command               | Description                                        |
| --------------------- | -------------------------------------------------- |
| `/verify setup`       | Open the interactive setup wizard                  |
| `/verify-view`        | View the current server verification configuration |
| `/verify-set-method`  | Change the verification method                     |
| `/verify-set-role`    | Set the role granted after verification            |
| `/verify-set-min-age` | Set the minimum Discord account age                |
| `/verify-post`        | Publish the verification message                   |
| `/verify-reset`       | Reset verification settings to defaults            |

Administrative configuration commands require the appropriate server management permissions.

---

## 🔐 OAuth2 Verification

OAuth2 verification uses a short-lived, single-use state token.

The flow is:

```text
User clicks Verify
       │
       ▼
State token generated
(bound to guild + user)
       │
       ▼
Discord OAuth2 authorization
       │
       ▼
Discord redirects to callback
       │
       ▼
State token consumed
       │
       ▼
Authorization code exchanged
       │
       ▼
Discord identity retrieved
       │
       ▼
Identity checked against
the original Discord user
       │
       ▼
Verified role assigned
```

The OAuth2 state is consumed when used, preventing the same verification state from being replayed.

The authorized Discord account is also checked against the user who originally started the verification flow.

### Public Deployment

For local development, an OAuth2 callback such as:

```text
http://localhost:8080/oauth/callback
```

can be used for testing on the same machine.

For other Discord members to use OAuth2 verification, the bot needs to be hosted somewhere reachable from the public internet and the OAuth2 redirect URI must point to the public callback URL.

HTTPS should be used for production deployments.

---

## 📧 Email Verification

Email verification sends a one-time verification code through an SMTP server.

Configure:

```env
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_ADDRESS=
```

The email verification flow is:

```text
User clicks Verify
       │
       ▼
Email address submitted
       │
       ▼
Verification code generated
       │
       ▼
Code sent through SMTP
       │
       ▼
User enters code
       │
       ▼
Challenge validated
       │
       ▼
User verified
```

---

## 📱 Phone Verification

Phone verification uses the Twilio API to send verification codes through SMS.

Configure:

```env
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

Phone numbers are expected in international E.164 format:

```text
+14155551234
```

SMS verification requires an appropriately configured Twilio account and sender number.

---

## 🗄️ Data & Configuration

VerifyGuard stores per-server configuration in SQLite.

The database is created automatically when the bot starts.

The configuration system is designed so that:

* New servers receive the default configuration
* Individual settings can be updated without replacing the entire configuration
* Existing configurations are merged with new default settings
* Settings are cached in memory for frequently accessed operations
* Resetting a server removes its stored configuration and returns it to defaults

The SQLite database is created under:

```text
database/bot.db
```

Database files should not be committed to the repository.

---

## 🔒 Security Considerations

VerifyGuard includes several mechanisms intended to reduce common verification and abuse scenarios:

### Expiring challenges

Temporary CAPTCHA and verification codes are not intended to remain valid indefinitely.

### Single-use OAuth2 state

OAuth2 state tokens are consumed after use, preventing replay of the same state.

### Identity binding

OAuth2 verification checks that the Discord account completing authorization matches the Discord user who initiated the verification process.

### Permission checks

Administrative configuration commands require server management permissions.

### Role hierarchy validation

VerifyGuard checks whether the bot can actually assign the configured verification role before attempting to use it.

### Secret separation

Credentials for Discord, SMTP, Twilio, and OAuth2 are loaded through environment variables rather than being stored in per-server configuration.

---

## 📁 Project Structure

```text
discord-verification-bot/
│
├── assets/
│   └── fonts/
│
├── core/
│   ├── base.py
│   ├── challenge_store.py
│   ├── discord_oauth.py
│   ├── email_sender.py
│   ├── oauth_state.py
│   ├── prechecks.py
│   ├── service.py
│   └── sms_sender.py
│
├── modules/
│   ├── button.py
│   ├── captcha.py
│   ├── email_verification.py
│   ├── image_captcha.py
│   ├── oauth2_verification.py
│   ├── phone_verification.py
│   └── registry.py
│
├── settings/
│   ├── defaults.py
│   └── manager.py
│
├── ui/
│   └── setup_wizard.py
│
├── web/
│   └── server.py
│
├── bot.py
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🧱 Adding a New Verification Method

VerifyGuard is designed around the `VerificationModule` abstraction.

A new verification method implements the shared interface:

```python
class VerificationModule(ABC):

    @abstractmethod
    def build_entry_view(self, settings: dict) -> discord.ui.View:
        ...
```

The module is then registered in the verification registry.

This allows the bot's main verification flow to remain independent of the implementation details of each verification method.

Conceptually:

```text
                 VerificationModule
                        │
        ┌───────────────┼────────────────┐
        │               │                │
      Button          CAPTCHA          OAuth2
        │               │                │
      Email           Image            Phone
        │               │                │
        └───────────────┼────────────────┘
                        │
                        ▼
                Shared Service
```

This architecture makes it possible to extend VerifyGuard with additional verification mechanisms without duplicating role-assignment and verification-result handling.

---

## 🧪 Development

When developing VerifyGuard, keep verification-specific behavior inside its module and shared behavior inside `core/`.

A useful separation is:

```text
Discord interaction
        ↓
Verification module
        ↓
Core verification service
        ↓
Discord role / logging
```

This keeps Discord UI handling separate from the application's core verification behavior.

---

## ⚠️ Current Limitations

VerifyGuard is currently designed primarily as a **single-process application**.

Temporary challenge and OAuth2 state are stored in memory. This means that restarting the bot invalidates active temporary verification sessions.

The current architecture can be extended to use a shared state store such as Redis if distributed or multi-process deployment becomes necessary.

External verification methods such as email, SMS, and OAuth2 also require their respective third-party services and credentials.

---

## 🗺️ Roadmap

Potential future improvements include:

* [ ] Automated test suite
* [ ] Formal Python package configuration
* [ ] Rate limiting improvements
* [ ] Persistent challenge storage
* [ ] More verification methods
* [ ] Improved administrator configuration
* [ ] Verification analytics
* [ ] Production deployment documentation
* [ ] CI checks and automated testing

---

## 🤝 Contributing

Contributions, suggestions, and improvements are welcome.

Before submitting a change:

1. Keep verification logic inside the appropriate module.
2. Reuse shared core services where possible.
3. Avoid storing secrets in source code.
4. Keep changes focused and documented.
5. Add tests for important new behavior.

---

## 📄 License

This project is licensed under the MIT License.

See [`LICENSE`](LICENSE) for details.

---

## 👤 Author

**TheAliRh**

Built as a modular Discord verification system with a focus on extensibility, asynchronous Python, and security-conscious verification flows.
