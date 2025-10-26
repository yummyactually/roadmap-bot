import os
from dotenv import load_dotenv
import logging

load_dotenv()

# ===== ОСНОВНЫЕ НАСТРОЙКИ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)

# ===== НАСТРОЙКИ БАЗЫ ДАННЫХ =====
DB_ECHO = os.getenv("DB_ECHO", "False").lower() == "true"

# ===== НАСТРОЙКИ ЛОГИРОВАНИЯ =====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ===== НАСТРОЙКИ КАНАЛОВ =====
DEFAULT_PARSE_MODE = "HTML"
MAX_MESSAGE_LENGTH = 4096

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
        
logger = logging.getLogger(__name__)
logger.info(LOG_LEVEL)

# ===== ПРОВЕРКА И ВЫВОД КОНФИГУРАЦИИ ====
def validate_config():
    """Проверка конфигурации"""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("ВНИМАНИЕ: BOT_TOKEN не установлен!")
        logger.error("Установите токен в .env файле")
        return False
        
    if ADMIN_ID == 0:
        logger.error("ВНИМАНИЕ: ADMIN_ID не установлен!")
        logger.error("Установите ваш Telegram ID в .env файле")

    return True