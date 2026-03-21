#!/usr/bin/env python3
"""
AION Onboarding — Einmaliger Setup-Wizard.
Wird automatisch beim ersten Start aufgerufen.
"""
import os
import sys
import json
import re

# UTF-8 auf Windows
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

BOT_DIR = Path(__file__).parent

# ── ANSI Farben ───────────────────────────────────────────────────────────────
_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

C_CYAN   = "96"
C_BOLD   = "1"
C_GREEN  = "92"
C_YELLOW = "93"
C_RED    = "91"
C_DIM    = "90"
C_WHITE  = "97"
C_LOGO   = "96;1"

# ── Hilfs-Funktionen ──────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  {_c(C_GREEN, '[OK]')}  {msg}")

def warn(msg: str) -> None:
    print(f"  {_c(C_YELLOW, '[!]')}   {msg}")

def err(msg: str) -> None:
    print(f"  {_c(C_RED, '[X]')}  {msg}")

def info(msg: str) -> None:
    print(f"  {_c(C_DIM, '...')}  {msg}")

def ask(prompt: str, default: str = "") -> str:
    """Zeigt Prompt, liest Eingabe, gibt Default zurück wenn leer."""
    hint = f" [{_c(C_DIM, default)}]" if default else ""
    try:
        val = input(f"  {_c(C_CYAN, prompt)}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise
    return val if val else default

def ask_hidden(prompt: str) -> str:
    """Versteckte Eingabe für API-Keys."""
    try:
        import getpass
        val = getpass.getpass(f"  {_c(C_CYAN, prompt)}: ")
        return val.strip()
    except Exception:
        return ask(prompt)

def section(title: str, step: str) -> None:
    print()
    print(f"  {_c(C_LOGO, '====================================================')} ")
    print(f"  {_c(C_BOLD, step)}  {_c(C_WHITE, title)}")
    print(f"  {_c(C_LOGO, '====================================================')} ")
    print()

# ── Modell-Tabelle ────────────────────────────────────────────────────────────
MODELS = {
    "gemini": [
        ("gemini-2.5-pro",        "Beste Qualitaet  · tiefes Reasoning  · langsam"),
        ("gemini-2.5-flash",      "Schnell & guenstig  (empfohlen)"),
        ("gemini-2.0-flash",      "Stabil & zuverlaessig"),
        ("gemini-2.0-flash-lite", "Ultra-schnell  · minimale Kosten"),
    ],
    "openai": [
        ("gpt-4.1",     "OpenAI Flagship  · beste Qualitaet"),
        ("gpt-4o",      "Multimodal  · Bilder & Audio"),
        ("o3",          "Deep Reasoning  · langsam & teuer"),
        ("o4-mini",     "Schnelles Reasoning  · guenstig  (empfohlen)"),
        ("gpt-4o-mini", "Ultra-schnell  · minimal"),
    ],
}

DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "openai": "o4-mini"}

# ── Banner ────────────────────────────────────────────────────────────────────

def banner() -> None:
    print()
    print(_c(C_LOGO, "  ===================================================="))
    print(_c(C_LOGO, "  =                                                  ="))
    print(_c(C_LOGO, "  =   AION  --  Erster Start: Einrichtung            ="))
    print(_c(C_LOGO, "  =                                                  ="))
    print(_c(C_LOGO, "  ===================================================="))
    print()
    print(f"  {_c(C_WHITE, 'Willkommen! Dieser Assistent wird AION einmalig einrichten.')}")
    print(f"  {_c(C_DIM, 'Alle Einstellungen koennen spaeter in .env und config.json geaendert werden.')}")
    print()

# ── Schritt 1: Provider ───────────────────────────────────────────────────────

def step1_provider() -> str:
    section("KI-Provider waehlen", "Schritt 1/6:")
    print(f"  {_c(C_DIM, 'Waehle deinen bevorzugten KI-Anbieter:')}")
    print()
    print(f"    {_c(C_WHITE, '1')}  {_c(C_CYAN, 'Google Gemini')}   {_c(C_DIM, '(empfohlen · guenstiger · schneller)')}")
    print(f"    {_c(C_WHITE, '2')}  {_c(C_CYAN, 'OpenAI')}          {_c(C_DIM, '(GPT-4.1, o3, o4-mini ...)')}")
    print()

    while True:
        choice = ask("Eingabe (1/2)", "1")
        if choice == "1":
            return "gemini"
        elif choice == "2":
            return "openai"
        else:
            warn("Bitte 1 oder 2 eingeben.")

# ── Schritt 2: API-Key ────────────────────────────────────────────────────────

def step2_apikey(provider: str) -> str:
    section("API-Key eingeben", "Schritt 2/6:")

    if provider == "gemini":
        print(f"  {_c(C_DIM, 'Kostenlos erstellen unter:')}")
        print(f"  {_c(C_CYAN, 'https://aistudio.google.com/app/apikey')}")
        print(f"  {_c(C_DIM, 'Format: AIza...')}")
    else:
        print(f"  {_c(C_DIM, 'Key erstellen unter:')}")
        print(f"  {_c(C_CYAN, 'https://platform.openai.com/api-keys')}")
        print(f"  {_c(C_DIM, 'Format: sk-...')}")
    print()

    while True:
        api_key = ask_hidden("API-Key eingeben")
        if not api_key:
            warn("API-Key darf nicht leer sein.")
            continue

        # Format-Validierung (soft warning)
        if provider == "gemini" and not api_key.startswith("AIza"):
            warn("Key beginnt nicht mit 'AIza' -- bist du sicher? (weiter mit Enter, neu eingeben mit n)")
            confirm = ask("Trotzdem verwenden? (j/n)", "j")
            if confirm.lower() == "n":
                continue
        elif provider == "openai" and not api_key.startswith("sk-"):
            warn("Key beginnt nicht mit 'sk-' -- bist du sicher? (weiter mit Enter, neu eingeben mit n)")
            confirm = ask("Trotzdem verwenden? (j/n)", "j")
            if confirm.lower() == "n":
                continue

        return api_key

# ── Schritt 3: Modell ─────────────────────────────────────────────────────────

def step3_model(provider: str) -> str:
    section("Modell waehlen", "Schritt 3/6:")

    model_list = MODELS[provider]
    default_model = DEFAULT_MODELS[provider]

    print(f"  {_c(C_DIM, 'Verfuegbare Modelle fuer')} {_c(C_CYAN, provider)}:")
    print()

    for i, (name, desc) in enumerate(model_list, 1):
        is_default = name == default_model
        marker = _c(C_GREEN, " *") if is_default else "  "
        num = _c(C_WHITE, str(i))
        model_name = _c(C_CYAN, f"{name:<26}")
        description = _c(C_DIM, desc)
        print(f"    {marker} {num}  {model_name}  {description}")

    print()
    print(f"  {_c(C_DIM, '* = Standard  |  Zahl eingeben oder Modellnamen direkt tippen')}")
    print()

    default_idx = next(
        (str(i) for i, (n, _) in enumerate(model_list, 1) if n == default_model),
        "1"
    )

    while True:
        choice = ask(f"Modell (1-{len(model_list)})", default_idx)

        # Nummer eingegeben
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(model_list):
                return model_list[idx - 1][0]
            else:
                warn(f"Bitte eine Zahl zwischen 1 und {len(model_list)} eingeben.")
                continue

        # Modellname direkt eingegeben
        known_names = [n for n, _ in model_list]
        if choice in known_names:
            return choice

        # Freier Name (evtl. zukuenftiges Modell)
        if choice:
            warn(f"Unbekanntes Modell '{choice}'. Trotzdem verwenden?")
            confirm = ask("Bestaetigen? (j/n)", "j")
            if confirm.lower() != "n":
                return choice

# ── Schritt 4: Telegram ───────────────────────────────────────────────────────

def step4_telegram() -> dict:
    section("Telegram (optional)", "Schritt 4/6:")
    print(f"  {_c(C_DIM, 'AION kann Nachrichten via Telegram senden und empfangen.')}")
    print()

    use_tg = ask("Telegram einrichten? (j/n)", "n")
    if use_tg.lower() != "j":
        info("Telegram uebersprungen.")
        return {}

    print()
    print(f"  {_c(C_DIM, 'Bot erstellen: @BotFather auf Telegram')}")
    print(f"  {_c(C_DIM, 'Chat-ID: Schreibe dem Bot und oeffne https://api.telegram.org/bot<TOKEN>/getUpdates')}")
    print()

    token = ask("Bot-Token (z.B. 123456:ABC-...)")
    chat_id = ask("Chat-ID (z.B. 123456789)")

    if not token or not chat_id:
        warn("Token oder Chat-ID fehlt -- Telegram nicht konfiguriert.")
        return {}

    ok("Telegram-Daten gespeichert.")
    return {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id}

# ── Schritt 5: Profil ─────────────────────────────────────────────────────────

def step5_profile() -> dict:
    section("Dein Profil", "Schritt 5/6:")
    print(f"  {_c(C_DIM, 'Damit AION sich besser auf dich einstellen kann.')}")
    print()

    name = ask("Dein Name", "")

    print()
    print(f"  {_c(C_DIM, 'Anrede:')}")
    print(f"    {_c(C_WHITE, '1')}  du    {_c(C_DIM, '(locker)')}")
    print(f"    {_c(C_WHITE, '2')}  Sie   {_c(C_DIM, '(formell)')}")
    anrede_choice = ask("Anrede (1/2)", "1")
    anrede = "du" if anrede_choice != "2" else "Sie"

    print()
    print(f"  {_c(C_DIM, 'Sprache:')}")
    print(f"    {_c(C_WHITE, '1')}  Deutsch")
    print(f"    {_c(C_WHITE, '2')}  Englisch")
    print(f"    {_c(C_WHITE, '3')}  gemischt")
    lang_choice = ask("Sprache (1/2/3)", "1")
    lang_map = {"1": "Deutsch", "2": "Englisch", "3": "gemischt"}
    lang = lang_map.get(lang_choice, "Deutsch")

    print()
    print(f"  {_c(C_DIM, 'Hauptnutzung (Mehrfachauswahl mit Komma, z.B. \"1,3\"):')}")
    print(f"    {_c(C_WHITE, '1')}  Coding")
    print(f"    {_c(C_WHITE, '2')}  Recherche")
    print(f"    {_c(C_WHITE, '3')}  Produktivitaet")
    print(f"    {_c(C_WHITE, '4')}  Kreatives Schreiben")
    print(f"    {_c(C_WHITE, '5')}  Allgemein")
    use_map = {"1": "Coding", "2": "Recherche", "3": "Produktivitaet",
               "4": "Kreatives Schreiben", "5": "Allgemein"}
    use_input = ask("Auswahl", "5")
    uses = []
    for part in use_input.split(","):
        part = part.strip()
        if part in use_map:
            uses.append(use_map[part])
    if not uses:
        uses = ["Allgemein"]

    print()
    print(f"  {_c(C_DIM, 'Antwort-Stil:')}")
    print(f"    {_c(C_WHITE, '1')}  Kurz & knapp")
    print(f"    {_c(C_WHITE, '2')}  Normal")
    print(f"    {_c(C_WHITE, '3')}  Ausfuehrlich")
    style_choice = ask("Stil (1/2/3)", "2")
    style_map = {"1": "Kurz & knapp", "2": "Normal", "3": "Ausfuehrlich"}
    style = style_map.get(style_choice, "Normal")

    print()
    extra = ask("Gibt es etwas, das AION von Anfang an wissen soll? (optional, Enter = ueberspringen)", "")

    return {
        "name": name,
        "anrede": anrede,
        "lang": lang,
        "uses": uses,
        "style": style,
        "extra": extra,
    }

# ── Schritt 6: System-Check ───────────────────────────────────────────────────

def step6_systemcheck(provider: str, api_key: str, model: str) -> bool:
    section("System-Check", "Schritt 6/6:")

    all_ok = True

    # 1. Dateisystem
    info("Dateisystem ...")
    try:
        test_file = BOT_DIR / "_onboarding_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        ok("Dateisystem beschreibbar")
    except Exception as e:
        err(f"Dateisystem-Fehler: {e}")
        all_ok = False

    # 2. Internetverbindung
    info("Internetverbindung ...")
    try:
        import urllib.request
        urllib.request.urlopen("https://www.google.com", timeout=5)
        ok("Internetverbindung vorhanden")
    except Exception as e:
        warn(f"Kein Internet oder Google nicht erreichbar: {e}")

    # 3. API-Test
    info(f"API-Test ({provider}) ...")
    try:
        if provider == "gemini":
            try:
                import google.genai as genai
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=model,
                    contents="Reply with exactly: OK"
                )
                reply = ""
                if hasattr(resp, "text"):
                    reply = resp.text
                elif hasattr(resp, "candidates"):
                    reply = resp.candidates[0].content.parts[0].text
                if reply.strip():
                    ok(f"Gemini API antwortet: {reply.strip()[:40]}")
                else:
                    warn("Gemini API antwortet, aber leer")
            except ImportError:
                warn("google-genai nicht installiert -- API-Test uebersprungen")
        else:
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                    max_tokens=5
                )
                reply = resp.choices[0].message.content or ""
                ok(f"OpenAI API antwortet: {reply.strip()[:40]}")
            except ImportError:
                warn("openai nicht installiert -- API-Test uebersprungen")
    except Exception as e:
        err(f"API-Test fehlgeschlagen: {e}")
        all_ok = False

    # 4. Plugin-Verzeichnis
    info("Plugins ...")
    plugins_dir = BOT_DIR / "plugins"
    if plugins_dir.exists():
        count = sum(1 for p in plugins_dir.iterdir() if p.is_dir())
        ok(f"Plugin-Verzeichnis gefunden: {count} Plugin(s)")
    else:
        warn("Plugin-Verzeichnis nicht gefunden")

    return all_ok

# ── Ausgabe schreiben ─────────────────────────────────────────────────────────

def write_env(provider: str, api_key: str, model: str, telegram: dict) -> None:
    env_path = BOT_DIR / ".env"
    lines = ["# AION Konfiguration - generiert von onboarding.py"]

    if provider == "gemini":
        lines.append(f"GEMINI_API_KEY={api_key}")
    else:
        lines.append(f"OPENAI_API_KEY={api_key}")

    lines.append(f"AION_MODEL={model}")
    lines.append("AION_PORT=7000")

    if telegram.get("TELEGRAM_BOT_TOKEN"):
        lines.append(f"TELEGRAM_BOT_TOKEN={telegram['TELEGRAM_BOT_TOKEN']}")
    if telegram.get("TELEGRAM_CHAT_ID"):
        lines.append(f"TELEGRAM_CHAT_ID={telegram['TELEGRAM_CHAT_ID']}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f".env geschrieben ({env_path})")


def write_config(model: str) -> None:
    config_path = BOT_DIR / "config.json"
    cfg = {}
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg["model"] = model
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"config.json geschrieben ({config_path})")


def update_character_md(profile: dict) -> None:
    char_path = BOT_DIR / "character.md"
    content = ""
    if char_path.exists():
        content = char_path.read_text(encoding="utf-8")

    # Bestehenden Nutzer-Profil-Abschnitt entfernen
    content = re.sub(
        r"\n## Nutzer-Profil \(Onboarding\).*",
        "",
        content,
        flags=re.DOTALL
    )
    content = content.rstrip()

    # Neuen Abschnitt anhaengen
    name   = profile.get("name", "")
    anrede = profile.get("anrede", "du")
    lang   = profile.get("lang", "Deutsch")
    uses   = ", ".join(profile.get("uses", ["Allgemein"]))
    style  = profile.get("style", "Normal")
    extra  = profile.get("extra", "")

    section_lines = [
        "",
        "",
        "## Nutzer-Profil (Onboarding)",
        f"- Name: {name}" if name else "- Name: (nicht angegeben)",
        f"- Anrede: {anrede}",
        f"- Sprache: {lang}",
        f"- Hauptnutzung: {uses}",
        f"- Antwort-Stil: {style}",
    ]
    if extra:
        section_lines.append(f"- Notiz: {extra}")

    content += "\n".join(section_lines) + "\n"
    char_path.write_text(content, encoding="utf-8")
    ok(f"character.md aktualisiert ({char_path})")


def write_flag() -> None:
    flag_path = BOT_DIR / "aion_onboarding_complete.flag"
    flag_path.write_text("Onboarding abgeschlossen.\n", encoding="utf-8")
    ok(f"Flag-Datei erstellt ({flag_path})")


def abschluss_banner(model: str, name: str) -> None:
    print()
    greeting = f"Hallo, {name}! AION ist bereit." if name else "AION ist bereit."
    print(_c(C_GREEN, "  ===================================================="))
    print(_c(C_GREEN, "  Einrichtung abgeschlossen!"))
    print(f"  {_c(C_DIM, 'Modell: ')}{_c(C_CYAN, model)}")
    print(f"  {_c(C_WHITE, greeting)}")
    print(_c(C_GREEN, "  ===================================================="))
    print()

# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_onboarding() -> None:
    try:
        banner()

        provider  = step1_provider()
        api_key   = step2_apikey(provider)
        model     = step3_model(provider)
        telegram  = step4_telegram()
        profile   = step5_profile()
        _ok       = step6_systemcheck(provider, api_key, model)

        # Ausgabe schreiben
        print()
        section("Konfiguration speichern", "Speichern:")

        write_env(provider, api_key, model, telegram)
        write_config(model)
        update_character_md(profile)
        write_flag()

        abschluss_banner(model, profile.get("name", ""))

    except KeyboardInterrupt:
        print()
        print()
        warn("Onboarding abgebrochen (Strg+C).")
        sys.exit(1)
    except Exception as e:
        print()
        err(f"Unerwarteter Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_onboarding()
