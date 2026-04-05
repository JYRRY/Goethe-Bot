# JYRY AI - Goethe-Institut Terminbenachrichtigungsbot

Telegram-Bot zur automatischen Überwachung von Prüfungsterminen am Goethe-Institut mit Echtzeit-Benachrichtigungen.

## Funktionen

- Automatische Überwachung von Goethe-Institut Prüfungsterminen
- Sofortige Telegram-Benachrichtigung bei neuen verfügbaren Terminen
- Unterstützung für mehrere Länder und Städte
- Kanal-Mitgliedschaftsprüfung (Force Join)
- Duplikat-Erkennung (keine doppelten Benachrichtigungen)

## Unterstützte Standorte

| Land | Städte |
|------|--------|
| Ägypten | Alexandria, Dokki, Hurghada |
| Marokko | Casablanca, Rabat |
| Algerien | Algier |
| Saudi-Arabien | Riad, Dschidda |
| Libanon | Beirut |

## Prüfungstypen

A1, A2, B1, B2, C1, C2

## Bot-Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/start` | Bot starten / Neues Abo erstellen |
| `/meineabos` | Aktive Abos anzeigen |
| `/stop` | Alle Benachrichtigungen stoppen |
| `/hilfe` | Hilfe anzeigen |

## Schnellstart

### Voraussetzungen

- Python 3.11+
- Telegram Bot Token (von [@BotFather](https://t.me/BotFather))

### Installation

1. Repository klonen:
```bash
git clone https://github.com/JYRRY/Goethe-Bot.git
cd Goethe-Bot
```

2. Virtuelle Umgebung erstellen:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
```

3. Abhängigkeiten installieren:
```bash
pip install -r requirements.txt
playwright install chromium
```

4. Umgebungsvariablen konfigurieren:
```bash
cp .env.example .env
# .env-Datei bearbeiten und BOT_TOKEN eintragen
```

5. Bot starten:
```bash
python -m bot.main
```

### Docker

```bash
# .env-Datei erstellen
cp .env.example .env
# BOT_TOKEN in .env eintragen

# Starten
docker compose up -d

# Logs anzeigen
docker compose logs -f

# Stoppen
docker compose down
```

## Konfiguration (.env)

| Variable | Beschreibung | Standard |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot Token | (erforderlich) |
| `REQUIRED_CHANNEL_ID` | Telegram-Kanal für Force Join | `@JYRYGROUP` |
| `SCRAPE_INTERVAL_MINUTES` | Scraping-Intervall in Minuten | `3` |
| `DATABASE_PATH` | Pfad zur SQLite-Datenbank | `data/goethe_bot.db` |
| `LOG_LEVEL` | Log-Level | `INFO` |

## Architektur

```
bot/          - Telegram Bot (Handler, Keyboards, Nachrichten)
scraper/      - Playwright Scraper (Browser-Automatisierung)
database/     - SQLite Datenbankschicht
notifications/ - Benachrichtigungssystem
data/         - Standort- und Prüfungsdaten
```

## Tech Stack

- **Python 3.11+**
- **python-telegram-bot** - Telegram Bot Framework
- **Playwright** - Browser-Automatisierung (Chromium)
- **SQLite + aiosqlite** - Datenbank
- **Docker** - Deployment

## Skalierung

- **Mehr Länder**: `data/locations.py` erweitern
- **Höhere Last**: PostgreSQL statt SQLite, Redis für Caching
- **Mehrere Instanzen**: Scraper als separaten Service auslagern
- **Monetarisierung**: Premium-Abos mit kürzerem Intervall, mehr Standorte

## Lizenz

MIT
