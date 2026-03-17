#!/usr/bin/env bash
# ============================================================
#  CellClaw — Install & Setup Script
#  Usage: bash install.sh
# ============================================================

set -e

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }
prompt()  { echo -e "${CYAN}${BOLD}$*${NC}"; }

# ── Banner ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}"
cat << 'EOF'
   ___  __  __ ___ ___ ___ ___ _      _   _    __
  / _ \|  \/  |_ _/ __/ __/ __| |    /_\ | |  / /
 | (_) | |\/| || | (__\__ \__ \ |__ / _ \| |_/ _ \
  \___/|_|  |_|___\___|___/___/____/_/ \_\____\___/
                                        🧬 v1.0
EOF
echo -e "${NC}"
echo -e "${BOLD}  AI Bioinformatics Engineer on Discord${NC}"
echo -e "  SSH-based remote HPC/workstation control via natural language"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Check Python ─────────────────────────────────────────────
info "Checking Python version..."
if ! command -v python3 &>/dev/null; then
    error "Python 3 not found. Please install Python 3.9 or higher."
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo $PY_VER | cut -d. -f1)
PY_MINOR=$(echo $PY_VER | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    error "Python 3.9+ required, found $PY_VER"
fi
success "Python $PY_VER found"

# ── Create virtualenv ─────────────────────────────────────────
VENV_DIR="$(pwd)/venv"
if [ -d "$VENV_DIR" ]; then
    warn "Virtual environment already exists at $VENV_DIR, skipping creation."
else
    info "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    success "Virtual environment created"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
info "Virtual environment activated"

# ── Install dependencies ──────────────────────────────────────
info "Installing dependencies from requirements.txt ..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
success "Dependencies installed"

# ── .env setup ───────────────────────────────────────────────
ENV_FILE="$(pwd)/.env"

if [ -f "$ENV_FILE" ]; then
    echo ""
    warn ".env file already exists."
    read -p "  Overwrite and reconfigure? [y/N] " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[Yy]$ ]]; then
        echo ""
        success "Keeping existing .env — skipping configuration."
        echo ""
        echo "  To reconfigure, delete .env and run: bash install.sh"
        echo ""
        echo ""
        echo "  Start the bot:  bash start.sh"
        echo ""
        exit 0
    fi
fi

# ── Interactive configuration wizard ─────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
prompt "  ⚙️  Configuration Wizard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Discord Bot Token ──────────────────────────────────────
echo -e "${BOLD}[1/4] Discord Bot Token${NC}"
echo "  → Go to https://discord.com/developers/applications"
echo "  → Create a bot → Bot → Reset Token → Copy"
echo ""
while true; do
    read -p "  Discord Bot Token: " DISCORD_TOKEN
    if [ -z "$DISCORD_TOKEN" ]; then
        warn "Token cannot be empty. Please try again."
    elif [ ${#DISCORD_TOKEN} -lt 50 ]; then
        warn "Token looks too short. Please double-check."
    else
        break
    fi
done
success "Discord token saved"
echo ""

# ── 2. LLM Provider ──────────────────────────────────────────
echo -e "${BOLD}[2/4] LLM Provider${NC}"
echo "  Supported providers:"
echo "  1) DeepSeek    (https://platform.deepseek.com)  — Recommended"
echo "  2) OpenAI      (https://platform.openai.com)"
echo "  3) Kimi        (https://platform.moonshot.cn)"
echo "  4) Other       (any OpenAI-compatible API)"
echo ""
read -p "  Choose provider [1-4, default=1]: " LLM_CHOICE
LLM_CHOICE=${LLM_CHOICE:-1}

case $LLM_CHOICE in
    1)
        LLM_BASE_URL="https://api.deepseek.com/v1"
        DEFAULT_MODEL="deepseek-chat"
        PROVIDER_NAME="DeepSeek"
        ;;
    2)
        LLM_BASE_URL="https://api.openai.com/v1"
        DEFAULT_MODEL="gpt-4o"
        PROVIDER_NAME="OpenAI"
        ;;
    3)
        LLM_BASE_URL="https://api.moonshot.cn/v1"
        DEFAULT_MODEL="moonshot-v1-8k"
        PROVIDER_NAME="Kimi"
        ;;
    4)
        read -p "  API Base URL: " LLM_BASE_URL
        DEFAULT_MODEL="your-model-name"
        PROVIDER_NAME="Custom"
        ;;
    *)
        LLM_BASE_URL="https://api.deepseek.com/v1"
        DEFAULT_MODEL="deepseek-chat"
        PROVIDER_NAME="DeepSeek"
        ;;
esac

echo ""
read -p "  $PROVIDER_NAME API Key: " LLM_API_KEY
while [ -z "$LLM_API_KEY" ]; do
    warn "API Key cannot be empty."
    read -p "  $PROVIDER_NAME API Key: " LLM_API_KEY
done

echo ""
read -p "  Model name [default: $DEFAULT_MODEL]: " LLM_MODEL
LLM_MODEL=${LLM_MODEL:-$DEFAULT_MODEL}
success "LLM configured: $PROVIDER_NAME / $LLM_MODEL"
echo ""

# ── 3. HTTP Proxy (optional) ──────────────────────────────────
echo -e "${BOLD}[3/4] HTTP Proxy (optional)${NC}"
echo "  Required if your machine needs a proxy to reach Discord/LLM APIs."
echo "  Example: http://127.0.0.1:7890"
echo "  Leave empty to skip."
echo ""
read -p "  HTTP Proxy [optional]: " HTTP_PROXY
if [ -n "$HTTP_PROXY" ]; then
    success "Proxy set: $HTTP_PROXY"
else
    info "No proxy configured"
fi
echo ""

# ── 4. Bot personality (optional) ────────────────────────────
echo -e "${BOLD}[4/4] Bot Identity (optional)${NC}"
echo "  Customize your bot's name and personality."
read -p "  Bot name [default: CellClaw]: " BOT_NAME
BOT_NAME=${BOT_NAME:-CellClaw}
success "Bot name: $BOT_NAME"
echo ""

# ── Write .env ────────────────────────────────────────────────
info "Writing .env ..."

cat > "$ENV_FILE" << EOF
# CellClaw Configuration
# Generated by install.sh — $(date)
# ⚠️  DO NOT commit this file to git!

# ── Discord ────────────────────────────────────────────────
DISCORD_TOKEN=${DISCORD_TOKEN}

# ── LLM ────────────────────────────────────────────────────
OMICS_LLM_BASE_URL=${LLM_BASE_URL}
OMICS_LLM_API_KEY=${LLM_API_KEY}
OMICS_LLM_MODEL=${LLM_MODEL}
OMICS_LLM_MAX_TOKENS=4096

# ── Proxy ──────────────────────────────────────────────────
$([ -n "$HTTP_PROXY" ] && echo "OMICS_LLM_PROXY=${HTTP_PROXY}" || echo "# OMICS_LLM_PROXY=http://127.0.0.1:7890")

# ── Bot ────────────────────────────────────────────────────
OMICS_BOT_NAME=${BOT_NAME}

# ── Data directory ─────────────────────────────────────────
# OMICSCLAW_DATA=./data
EOF

success ".env written"

# ── Make scripts executable ───────────────────────────────────
chmod +x start.sh stop.sh restart.sh 2>/dev/null || true

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}${BOLD}  ✅ Installation complete!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Before starting, make sure your Discord bot is:"
echo "  1. Invited to your server with Message Content Intent enabled"
echo "  2. Go to Developer Portal → Bot → Privileged Gateway Intents"
echo "     ✓ MESSAGE CONTENT INTENT"
echo ""
echo "  Start the bot:"
echo -e "    ${BOLD}bash start.sh${NC}"
echo ""
echo "  View logs:"
echo -e "    ${BOLD}tail -f /tmp/omicsclaw_bot.log${NC}"
echo ""
echo "  Stop the bot:"
echo -e "    ${BOLD}bash stop.sh${NC}"
echo ""
echo "  Add your first server in Discord:"
echo -e "    ${BOLD}/server add --name myserver --host 10.0.0.1 --user ubuntu --key ~/.ssh/id_rsa${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
