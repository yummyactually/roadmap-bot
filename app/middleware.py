from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from database import async_sessionmaker
from config import LOG_LEVEL
import logging

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
        
logger = logging.getLogger(__name__)
logger.info(__name__)

class DatabaseMiddleware(BaseMiddleware):
    """Middleware для автоматического предоставления сессии БД в обработчики"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Создает сессию БД и передает ее в обработчик"""
        async with async_sessionmaker() as session:
            try:
                data['session'] = session
                
                if 'bot' not in data:
                    data['bot'] = data.get('event_router', {}).get('bot')
                
                result = await handler(event, data)
                
                await session.commit()
                
                return result
                
            except Exception as e:
                await session.rollback()
                logger.warning(f"Ошибка в middleware БД: {e}")
                return None
            finally:
                await session.close()