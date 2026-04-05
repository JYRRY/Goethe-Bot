"""German message templates for JYRY AI bot — B2 only."""

from bot.config import REQUIRED_CHANNEL_ID

WELCOME = (
    "Willkommen bei *JYRY AI* \\- deinem Goethe\\-Institut B2 Terminbenachrichtigungsbot\\! 🎓\n\n"
    "Ich überwache verfügbare *B2\\-Prüfungstermine* am Goethe\\-Institut und "
    "benachrichtige dich sofort, wenn neue Plätze frei werden\\.\n\n"
    "Wähle dein *Land* aus:"
)

CHANNEL_REQUIRED = (
    "⚠️ Du musst zuerst unserem Kanal beitreten, bevor du den Bot nutzen kannst\\.\n\n"
    f"👉 Tritt hier bei: {REQUIRED_CHANNEL_ID}\n\n"
    "Danach drücke /start erneut\\."
)

SELECT_CITY = "Wähle deine *Stadt* aus \\(B2\\-Prüfung\\):"

SUBSCRIPTION_ADDED = (
    "✅ *Abo erstellt\\!*\n\n"
    "📍 Land: {country}\n"
    "🏙 Stadt: {city}\n"
    "📝 Prüfung: *B2*\n\n"
    "Du wirst benachrichtigt, sobald neue B2\\-Termine verfügbar sind\\.\n\n"
    "Weitere Optionen:\n"
    "/start \\- Weitere Stadt hinzufügen\n"
    "/meineabos \\- Meine Abos anzeigen\n"
    "/stop \\- Alle Benachrichtigungen stoppen"
)

NO_SUBSCRIPTIONS = "Du hast noch keine aktiven Abos\\. Drücke /start, um eines zu erstellen\\."

MY_SUBSCRIPTIONS_HEADER = "📋 *Deine aktiven B2\\-Abos:*\n\n"

SUBSCRIPTION_ITEM = "• B2 in {city} \\({country}\\)"

SUBSCRIPTION_REMOVED = "🗑 Abo wurde entfernt\\."

ALL_STOPPED = (
    "🛑 Alle Benachrichtigungen wurden gestoppt\\.\n\n"
    "Drücke /start, um neue Abos zu erstellen\\."
)

HELP_TEXT = (
    "*JYRY AI \\- Hilfe*\n\n"
    "Dieser Bot überwacht *B2\\-Prüfungstermine* am Goethe\\-Institut "
    "und benachrichtigt dich bei neuen verfügbaren Plätzen\\.\n\n"
    "*Befehle:*\n"
    "/start \\- Bot starten / Neues Abo\n"
    "/meineabos \\- Aktive Abos anzeigen\n"
    "/stop \\- Alle Abos deaktivieren\n"
    "/hilfe \\- Diese Hilfe anzeigen\n\n"
    "*So funktioniert es:*\n"
    "1\\. Wähle ein Land\n"
    "2\\. Wähle eine Stadt\n"
    "3\\. Warte auf B2\\-Benachrichtigungen\\!"
)

APPOINTMENT_ALERT = (
    "🔔 *Neuer B2\\-Prüfungstermin verfügbar\\!*\n\n"
    "📅 Datum: {date}\n"
    "🕐 Uhrzeit: {time}\n"
    "📍 Standort: {city}, {country}\n"
    "📊 Verfügbarkeit: {slots}\n"
)

APPOINTMENT_ALERT_WITH_LINK = APPOINTMENT_ALERT + "\n[👉 Jetzt buchen\\!]({booking_url})"

ERROR_GENERIC = "❌ Ein Fehler ist aufgetreten\\. Bitte versuche es erneut\\."
