import asyncio
from aiogram import Router, F
from aiogram.types import Message
from cache.redis_manager import redis_cache
from cache.mongo_manager import mongo_storage
from config import config

router = Router()

# Для отслеживания удаленных сообщений нам нужно использовать polling
# или webhook с обработкой update'ов. Вот упрощенный вариант:

async def monitor_deleted_messages(bot, chat_id: int):
    """Мониторинг удаленных сообщений (упрощенный)"""
    # В реальном боте это было бы через вебхук или отдельный polling
    pass

@router.message(F.content_type == "left_chat_member")
async def handle_user_left(message: Message):
    """Обработка выхода пользователя из чата"""
    try:
        # Можем сохранить информацию о выходе
        left_user = message.left_chat_member
        
        event_data = {
            "type": "user_left",
            "chat_id": message.chat.id,
            "user_id": left_user.id,
            "username": left_user.username,
            "first_name": left_user.first_name,
            "timestamp": message.date.isoformat() if message.date else None
        }
        
        # Сохраняем в MongoDB
        await mongo_storage.save_message({
            "message_id": message.message_id,
            "chat_id": message.chat.id,
            "type": "event",
            "event_data": event_data,
            "created_at": message.date.isoformat() if message.date else None
        })
        
    except Exception as e:
        print(f"Ошибка обработки выхода пользователя: {e}")

# В реальном боте для отслеживания удаленных сообщений нужно:
# 1. Хранить ID всех сообщений в чате
# 2. Периодически проверять, какие сообщения исчезли
# 3. Помечать их как удаленные
