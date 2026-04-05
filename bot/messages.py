"""German message templates for JYRY AI bot."""

from bot.config import REQUIRED_CHANNEL_ID

WELCOME = (
    "Willkommen bei *JYRY AI* \\- deinem Goethe\\-Institut Terminbenachrichtigungsbot\\! 🎓\n\n"
    "Ich überwache verfügbare Prüfungstermine am Goethe\\-Institut und "
    "benachrichtige dich sofort, wenn neue Plätze frei werden\\.\n\n"
    "Wähle zuerst dein *Land* aus:"
)

CHANNEL_REQUIRED = (
    "⚠️ Du musst zuerst unserem Kanal beitreten, bevor du den Bot nutzen kannst\\.\n\n"
    f"👉 Tritt hier bei: {REQUIRED_CHANNEL_ID}\n\n"
    "Danach drücke /start erneut\\."
)

SELECT_CITY = "Wähle deine *Stadt* aus:"

SELECT_EXAM = "Wähle den *Prüfungstyp* aus:"

SUBSCRIPTION_ADDED = (
    "✅ *Abo erstellt\\!*\n\n"
    "📍 Land: {country}\n"
    "🏙 Stadt: {city}\n"
    "📝 Prüfung: {exam_type}\n\n"
    "Du wirst benachrichtigt, sobald neue Termine verfügbar sind\\.\n\n"
    "Weitere Optionen:\n"
    "/start \\- Neues Abo hinzufügen\n"
    "/meineabos \\- Meine Abos anzeigen\n"
    "/stop \\- Alle Benachrichtigungen stoppen"
)

NO_SUBSCRIPTIONS = "Du hast noch keine aktiven Abos\\. Drücke /start, um eines zu erstellen\\."

MY_SUBSCRIPTIONS_HEADER = "📋 *Deine aktiven Abos:*\n\n"

SUBSCRIPTION_ITEM = "• {exam_type} in {city} \\({country}\\)"

SUBSCRIPTION_REMOVED = "🗑 Abo wurde entfernt\\."

ALL_STOPPED = (
    "🛑 Alle Benachrichtigungen wurden gestoppt\\.\n\n"
    "Drücke /start, um neue Abos zu erstellen\\."
)

HELP_TEXT = (
    "*JYRY AI \\- Hilfe*\n\n"
    "Dieser Bot überwacht Prüfungstermine am Goethe\\-Institut "
    "und benachrichtigt dich bei neuen verfügbaren Plätzen\\.\n\n"
    "*Befehle:*\n"
    "/start \\- Bot starten / Neues Abo\n"
    "/meineabos \\- Aktive Abos anzeigen\n"
    "/stop \\- Alle Abos deaktivieren\n"
    "/hilfe \\- Diese Hilfe anzeigen\n\n"
    "*So funktioniert es:*\n"
    "1\\. Wähle ein Land\n"
    "2\\. Wähle eine Stadt\n"
    "3\\. Wähle den Prüfungstyp \\(A1\\-C2\\)\n"
    "4\\. Warte auf Benachrichtigungen\\!"
)

APPOINTMENT_ALERT = (
    "🔔 *Neuer Prüfungstermin verfügbar\\!*\n\n"
    "📝 Prüfung: *{exam_type}*\n"
    "📅 Datum: {date}\n"
    "🕐 Uhrzeit: {time}\n"
    "📍 Standort: {city}, {country}\n"
    "📊 Verfügbarkeit: {slots}\n"
)

APPOINTMENT_ALERT_WITH_LINK = APPOINTMENT_ALERT + "\n[👉 Jetzt buchen\\!]({booking_url})"

ERROR_GENERIC = "❌ Ein Fehler ist aufgetreten\\. Bitte versuche es erneut\\."
