#!/usr/bin/env bash
# AION Start Script — macOS / Linux
# Usage: bash start.sh [web|cli]
#        or double-click / ./start.sh

set -e
cd "$(dirname "$0")"

# Colors
RESET='\033[0m'; BOLD='\033[1m'; CYAN='\033[96m'; GREEN='\033[92m'
YELLOW='\033[93m'; RED='\033[91m'; GRAY='\033[90m'

clear
echo
echo -e "${CYAN}${BOLD}  ===================================================="
echo -e "  =   AION  -  Autonomous Intelligent Operations   ="
echo -e "  ====================================================${RESET}"
echo

# --- [1/3] Python ---
echo -e "${BOLD}  --- [1/3] Python ---${RESET}"
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}  [ERROR]  python3 not found. Install: brew install python3${RESET}"
  exit 1
fi
echo -e "${GREEN}  [OK]  $(python3 --version)${RESET}"
echo

# --- [2/3] Packages ---
echo -e "${BOLD}  --- [2/3] Packages ---${RESET}"
python3 -m pip install -r requirements.txt -q
python3 -m pip install google-genai requests duckduckgo-search edge-tts -q
echo -e "${GREEN}  [OK]  Packages ready${RESET}"
echo

# --- [3/3] Config ---
echo -e "${BOLD}  --- [3/3] Config ---${RESET}"
if [ ! -f ".env" ]; then
  echo -e "${YELLOW}  [!]  .env missing — running setup${RESET}"
  echo
  read -p "  OpenAI API Key  (sk-...):   " OPENAI_KEY
  read -p "  Gemini API Key  (AIza...):  " GEMINI_KEY
  read -p "  Telegram Token  (optional): " TG_TOKEN
  read -p "  Telegram Chat-ID (optional):" TG_CHAT
  read -p "  Start model (default: gemini-2.0-flash): " MODEL_INPUT
  [ -z "$MODEL_INPUT" ] && MODEL_INPUT="gemini-2.0-flash"
  if [ -z "$OPENAI_KEY" ] && [ -z "$GEMINI_KEY" ]; then
    echo -e "${RED}  ERROR: At least one API key required.${RESET}"; exit 1
  fi
  {
    echo "# AION Config"
    [ -n "$OPENAI_KEY" ] && echo "OPENAI_API_KEY=$OPENAI_KEY"
    [ -n "$GEMINI_KEY" ] && echo "GEMINI_API_KEY=$GEMINI_KEY"
    [ -n "$TG_TOKEN"   ] && echo "TELEGRAM_BOT_TOKEN=$TG_TOKEN"
    [ -n "$TG_CHAT"    ] && echo "TELEGRAM_CHAT_ID=$TG_CHAT"
    echo "AION_MODEL=$MODEL_INPUT"
    echo "AION_PORT=7000"
  } > .env
  echo -e "${GREEN}  [OK]  .env created${RESET}"
else
  echo -e "${GREEN}  [OK]  .env found${RESET}"
fi
echo

# --- Mode selection ---
MODE="${1:-}"
if [ -z "$MODE" ]; then
  echo -e "${CYAN}${BOLD}  ===================================================="
  echo -e "  =   How should AION start?                      ="
  echo -e "  ====================================================${RESET}"
  echo
  echo "  [1]  Web UI  --  Browser + localhost:7000"
  echo "  [2]  CLI     --  Terminal chat"
  echo
  read -p "  Choice (1/2, default: 1): " CHOICE
  [ -z "$CHOICE" ] && CHOICE="1"
  [ "$CHOICE" = "1" ] && MODE="web" || MODE="cli"
fi

if [ "$MODE" = "cli" ]; then
  clear
  python3 aion_cli.py
else
  # Kill any existing process on port 7000
  PID=$(lsof -ti :7000 2>/dev/null || true)
  [ -n "$PID" ] && kill -9 "$PID" 2>/dev/null && echo -e "${YELLOW}  [OK]  Freed port 7000 (PID $PID)${RESET}"

  echo -e "${CYAN}${BOLD}  ===================================================="
  echo -e "  =   AION Web UI starting                        ="
  echo -e "  =   URL:    http://localhost:7000               ="
  echo -e "  =   Stop:   Ctrl+C                              ="
  echo -e "  ====================================================${RESET}"
  echo

  # Open browser after 3s in background
  (sleep 3 && open "http://localhost:7000" 2>/dev/null || xdg-open "http://localhost:7000" 2>/dev/null || true) &

  python3 aion_web.py
fi
