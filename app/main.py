import asyncio
import sys
from datetime import datetime
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, ADMIN_ID, validate_config, LOG_LEVEL
from database import create_db, async_sessionmaker
from handlers import router as main_router
from middleware import DatabaseMiddleware

# ===== TELEGRAM BOT SETUP =====
async def setup_bot():
    """Настройка и запуск Telegram бота"""
    try:
        if not validate_config():
            logger.error("Ошибка конфигурации! Завершение работы.")
            return False
        
        logger.info("Инициализация RoadMap Telegram Bot...")
        
        await create_db()
        
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        dp = Dispatcher(storage=MemoryStorage())
        
        dp.message.middleware(DatabaseMiddleware())
        dp.callback_query.middleware(DatabaseMiddleware())
        
        dp["bot"] = bot
        
        dp.include_router(main_router)
        
        commands = [
            BotCommand(command="/start", description="🎯 Главное меню"),
            BotCommand(command="/help", description="❓ Справка"),
            BotCommand(command="/add_project", description="➕ Создать проект"),
            BotCommand(command="/add_task", description="📝 Добавить задачу"),
            BotCommand(command="/roadmap", description="🗺 Показать роадмапы"),
            BotCommand(command="/set_channel", description="📢 Настроить канал"),
            BotCommand(command="/update_task", description="🔄 Изменить статус задачи"),
            BotCommand(command="/admin", description="🔧 Админ панель"),
        ]
        await bot.set_my_commands(commands)
        
        me = await bot.get_me()
        logger.info(f"Бот запущен: @{me.username} (ID: {me.id})")
        
        try:
            startup_message = (
                f"🚀 <b>RoadMapEx запущен!</b>\n\n"
                f"🤖 Бот: @{me.username} (ID: {me.id})\n"
                f"📊 База данных: SQLite\n"
                f"⏰ Время запуска: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<b>📋 Доступные команды:</b>\n"
                f"/start - Главное меню\n"
                f"/add_project - Создать проект\n"
                f"/add_task - Добавить задачу\n"
                f"/roadmap - Показать роадмапы\n"
                f"/set_channel - Настроить канал\n"
                f"/update_task - Изменить статус задачи\n"
                f"/help - Подробная справка"
            )
            
            if ADMIN_ID != 0:
                await bot.send_message(ADMIN_ID, startup_message, parse_mode="HTML")
                logger.info(f"Уведомление отправлено администратору (ID: {ADMIN_ID})")
            
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление: {e}")
        
        logger.info("Запуск поллинга...")
        await dp.start_polling(bot, handle_signals=False)
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        if 'bot' in locals():
            await bot.session.close()
            logger.info("Соединение закрыто")

# ===== MAIN FUNCTION =====
async def main():
    """Главная функция - запуск Telegram бота"""
    logger.info("RoadMapEx - Telegram Bot")
    logger.info("=" * 40)
    
    if not validate_config():
        return False
    
    logger.info("Запуск Telegram бота...")
    await setup_bot()

if __name__ == "__main__":
    try:
        logging.basicConfig(
            level=LOG_LEVEL,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
                
        logger = logging.getLogger(__name__)
        logger.info(__name__)
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.warning("\nОстановка приложения...")
        
    except Exception as e:
        logger.warning(f"\nКритическая ошибка: {e}")
        logger.warning("Проверьте конфигурацию")
        sys.exit(1)