<div align="center">

<img src="static/aion-2026.svg" alt="AION" width="400">

**Autonomous Intelligent Operations Node**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688?style=flat-square)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Platforms](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)]()

</div>

---

AION is a self-hosted AI agent that **writes its own plugins**, routes tasks across 6 providers, and works while you sleep — running 100% on your machine.

> No cloud dependency beyond the LLM API. Everything else is local.

---

## Why AION?

**🧠 It extends itself.**
AION writes, hot-reloads, and creates its own plugins directly from chat. No manual skill files, no code editor. Just ask: *"Add a tool that checks Bitcoin prices."* The plugin is live immediately.

**🎭 A personality that grows with you.**
AION's character evolves automatically — mood adapts to context, communication style deepens over 300+ exchanges, and every morning it surfaces your unfinished tasks without being asked.

**💡 No API costs for everyday tasks.**
Connect your Claude.ai subscription ($20/mo) or Gemini free tier via OAuth. AION routes heavy tasks to powerful models and light tasks to free ones — automatically.

**🖱 Controls your desktop.**
Screenshot, click, type, hotkeys — AION sees and controls your screen via pyautogui, without a browser extension or separate daemon.

---

## AION vs. OpenClaw

Both are self-hosted, open-source AI agents with Web UI, MCP, scheduling, and semantic memory. Here's where they differ:

| | AION | OpenClaw |
|---|---|---|
| **Writes its own plugins from chat** | ✅ | ❌ |
| **Evolving personality + mood engine** | ✅ | ❌ |
| **Proactive morning briefings** | ✅ | ❌ |
| **Use subscription (no per-token cost)** | ✅ Claude + Gemini OAuth | ❌ API key required |
| **Desktop automation** (click, type, screenshot) | ✅ | ❌ |
| Web UI | ✅ | ✅ |
| Scheduled tasks / cron | ✅ | ✅ |
| MCP integrations | ✅ 1,700+ | ✅ plugin-based |
| Semantic RAG memory | ✅ | ✅ |
| Browser automation | ✅ Playwright | ✅ exec-based |
| Messaging: Telegram, Discord, Slack | ✅ | ✅ |
| Messaging: WhatsApp, Signal, iMessage | ❌ | ✅ |
| Mobile companion app | ❌ | ✅ |
| AI providers | 6 (incl. Ollama) | 40+ |
| Runtime | Python | Node.js |

> OpenClaw is the better choice if you need WhatsApp/Signal/iMessage or a mobile companion app.
> AION is the better choice if you want an agent that evolves, extends itself, and thinks proactively.

---

## ⚡ Quick Start

```bash
pip install -r requirements.txt && pip install -e .
aion --setup    # guided setup: API keys, plugins, providers
aion            # ↑↓ arrow-key selector: Web UI or CLI
```

```bash
aion --web      # Web UI → http://localhost:7000
aion --cli      # CLI mode (terminal only)
aion update     # git pull + reinstall in one step
```

---

## Features

| | |
|---|---|
| 🤖 6 AI providers + automatic failover | 🔐 Credentials vault (AES-encrypted) |
| 🔀 Task routing — best model per task type | 📱 Messaging: Telegram, Discord, Slack, Alexa |
| 🧩 Plugin system — hot-reload, one Python file | 🤖 Multi-agent delegation |
| 🌐 Browser automation (Playwright, 8 tools) | 🎙 Audio: TTS + STT, voice in Telegram |
| ⏰ Scheduler (cron + interval + natural language) | 🔒 100% local — no cloud beyond the LLM API |
| 🔌 MCP client — 1,700+ server integrations | 🧠 Semantic RAG memory (vector embeddings) |

---

## Supported Providers

| Provider | Free option | Notes |
|---|---|---|
| **Google Gemini** | ✅ Free tier + Google OAuth | Recommended default |
| **Anthropic Claude** | ✅ Claude.ai subscription ($20/mo) | Best for coding + reasoning |
| **OpenAI** | — | GPT-4.1, o3, o4-mini |
| **DeepSeek** | — | Very low cost |
| **xAI Grok** | — | grok-3, grok-3-mini |
| **Ollama** | ✅ Fully local, offline | Any model, no API key |

Switch model any time: Web UI dropdown, `POST /api/model`, or just say *"Switch to claude-opus-4-6"*.

---

## Installation

### Guided (recommended)
```bash
pip install -r requirements.txt && pip install -e .
aion --setup
```

The setup wizard configures API keys, plugins, and providers. Everything can be changed later in the Web UI.

### Docker
```bash
docker-compose up
```
Playwright/Chromium pre-installed. Volumes for `.env`, config, memory, and plugins.

---

## Docs

| | |
|---|---|
| [⚙ Configuration & Troubleshooting](docs/configuration.md) | `.env`, `config.json`, task routing, file structure, troubleshooting |
| [🔌 Plugin Development](docs/plugins.md) | Writing plugins, tool registration, available plugins |
| [📡 REST API Reference](docs/api.md) | All endpoints, SSE stream events |
| [💬 Messaging & Integrations](docs/messaging.md) | Telegram, Discord, Slack, Alexa, Browser, MCP |

---

<div align="center">

Made with Python · Powered by your choice of AI

*AION is fully transparent — its codebase, prompts, and memory are always readable and editable.*

</div>
