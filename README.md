# Molty Royale AI Agent Bot

Autonomous AI agent for Molty Royale — handles account creation, identity registration, gameplay, and cross-game learning. Features a real-time web dashboard for live monitoring.

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy env template
cp .env.example .env

# 3. Run the bot (first run = interactive setup)
python -m bot.main
```

## 📊 Command Center Dashboard

The bot comes with a built-in real-time web dashboard!

When running locally, open: **http://localhost:8080**
When running on Railway, click the provided domain link.

**Features:**
- **Live Metrics**: Agents, Playing, Dead, Moltz, sMoltz, CROSS
- **Agent Overview**: Real-time status, HP/EP bars, Inventory, Enemies
- **Live Logs**: Real-time streaming log panel that auto-updates
- **Coming Soon**: Multi-account management, export/import, data analytics

## 🛠️ Configuration

| Env Variable | Default | Description |
|---|---|---|
| `ROOM_MODE` | `free` | `free` (default) / `auto` / `paid` |
| `ADVANCED_MODE` | `true` | Auto-manage Owner EOA & whitelist |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |
| `WEB_PORT` | `8080` | Port for the web dashboard |

## 🐳 Docker

```bash
docker build -t molty-bot .
docker run --env-file .env -p 8080:8080 -it molty-bot
```

## 🚂 Railway Deployment

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Molty Royale AI Agent"
git remote add origin https://github.com/YOUR_USER/molty5.git
git push -u origin main
```

### Step 2: Connect in Railway
1. Go to [railway.com](https://railway.com) → New Project → Deploy from GitHub
2. Select your `molty5` repo
3. Go to Settings → Networking → **Generate Domain** (to access the dashboard)

### Step 3: Set Variables in Railway Dashboard

Go to your service → **Variables** tab → add these:

**Required (You fill these):**
| Variable | Value | Description |
|---|---|---|
| `AGENT_NAME` | `YourBotName` | Agent name (max 50 chars) |
| `ADVANCED_MODE` | `true` | Bot auto-generates Owner EOA |
| `ROOM_MODE` | `free` | `free` / `auto` / `paid` |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RAILWAY_API_TOKEN` | *(see below)* | Required to auto-save credentials |

**Auto-generated (DO NOT FILL):**
| Variable | Description |
|---|---|
| `API_KEY` | Auto-filled after POST /accounts |
| `AGENT_WALLET_ADDRESS` | Auto-generated Agent EOA |
| `AGENT_PRIVATE_KEY` | Auto-generated Agent private key |
| `OWNER_EOA` | Auto-generated Owner EOA |
| `OWNER_PRIVATE_KEY` | Auto-generated Owner private key |

### Step 4: Create RAILWAY_API_TOKEN
1. Go to [railway.com/account/tokens](https://railway.com/account/tokens)
2. Create new token → copy
3. Add as `RAILWAY_API_TOKEN` in Variables

> *Why?* The bot uses this token to automatically save its generated API Keys and wallets directly into your Railway environment variables. This ensures persistence across redeploys without needing external databases.

## 🏗️ Architecture

```
bot/
├── main.py           # Entry point
├── heartbeat.py      # Main loop (state machine)
├── dashboard/        # Command Center Web UI
├── setup/            # Account + wallet + whitelist + identity
├── game/             # WebSocket engine + game strategy
├── strategy/         # Combat AI + movement + guardian farming
├── web3/             # EIP-712, contracts, wallet management
├── memory/           # Cross-game learning
└── utils/            # Logger, rate limiter, Railway sync
```
