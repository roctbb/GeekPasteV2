from config import *
import telebot  # pytelegrambotapi


# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'true').lower() in ['1', 'true', 'yes']


bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode=None)


def send_telegram_message(text: str):
    """
    Sends a text message to the configured Telegram chat.
    Silently no-ops if not configured or library missing.
    """
    if not TELEGRAM_ENABLED:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or not telebot:
        return
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text)
    except Exception as e:
        print(e)
