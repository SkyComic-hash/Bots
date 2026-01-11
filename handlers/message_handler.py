from datetime import datetime
from typing import Dict, Any
from aiogram import Router, F
from aiogram.types import Message, ContentType
from aiogram.filters import Command
from cache.redis_manager import redis_cache
from cache.mongo_manager import mongo_storage
from config import config

router = Router()

def extract_message_data(message: Message) -> Dict[str, Any]:
    """Извлечение данных из сообщения"""
    data = {
        "message_id": message.message_id,
        "chat_id": message.chat.id,
        "user_id": message.from_user.id if message.from_user else None,
        "username": message.from_user.username if message.from_user else None,
        "first_name": message.from_user.first_name if message.from_user else None,
        "last_name": message.from_user.last_name if message.from_user else None,
        "chat_type": message.chat.type,
        "chat_title": message.chat.title if message.chat.title else None,
        "created_at": message.date.isoformat() if message.date else datetime.now().isoformat(),
        "is_edited": False,
        "is_deleted": False,
        "has_media": False,
        "media_type": None,
        "file_id": None,
        "text": None,
        "caption": None,
        "entities": None,
        "reply_to_message_id": message.reply_to_message.message_id if message.reply_to_message else None,
        "forward_from": None,
        "forward_from_chat": None
    }
    
    # Текст
    if message.text:
        data["text"] = message.text
        data["entities"] = message.entities if message.entities else None
    
    # Подпись
    if message.caption:
        data["caption"] = message.caption
        data["caption_entities"] = message.caption_entities if message.caption_entities else None
    
    # Медиа
    if message.photo:
        data["has_media"] = True
        data["media_type"] = "photo"
        data["file_id"] = message.photo[-1].file_id
    elif message.video:
        data["has_media"] = True
        data["media_type"] = "video"
        data["file_id"] = message.video.file_id
    elif message.document:
        data["has_media"] = True
        data["media_type"] = "document"
        data["file_id"] = message.document.file_id
    elif message.audio:
        data["has_media"] = True
        data["media_type"] = "audio"
        data["file_id"] = message.audio.file_id
    elif message.voice:
        data["has_media"] = True
        data["media_type"] = "voice"
        data["file_id"] = message.voice.file_id
    elif message.sticker:
        data["has_media"] = True
        data["media_type"] = "sticker"
        data["file_id"] = message.sticker.file_id
    elif message.animation:
        data["has_media"] = True
        data["media_type"] = "animation"
        data["file_id"] = message.animation.file_id
    
    # Пересылка
    if message.forward_from:
        data["forward_from"] = {
            "id": message.forward_from.id,
            "username": message.forward_from.username,
            "first_name": message.forward_from.first_name
        }
    elif message.forward_from_chat:
        data["forward_from_chat"] = {
            "id": message.forward_from_chat.id,
            "title": message.forward_from_chat.title,
            "type": message.forward_from_chat.type
        }
    elif message.forward_sender_name:
        data["forward_from"] = {"name": message.forward_sender_name}
    
    return data

@router.message(F.content_type.in_({
    ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.DOCUMENT, ContentType.AUDIO, ContentType.VOICE,
    ContentType.STICKER, ContentType.ANIMATION
}))
async def handle_new_message(message: Message):
    """Обработка новых сообщений"""
    try:
        message_data = extract_message_data(message)
        
        # Сохраняем в Redis (кэш)
        await redis_cache.save_message(message_data)
        
        # Сохраняем в MongoDB (постоянное хранение)
        await mongo_storage.save_message(message_data)
        
        if config.DEBUG:
            print(f"📨 Сообщение сохранено: {message.chat.id}:{message.message_id}")
            
    except Exception as e:
        print(f"Ошибка обработки сообщения: {e}")

@router.edited_message()
async def handle_edited_message(message: Message):
    """Обработка отредактированных сообщений"""
    try:
        updates = {
            "text": message.text,
            "caption": message.caption,
            "edited_at": datetime.now().isoformat(),
            "is_edited": True
        }
        
        # Обновляем в Redis
        await redis_cache.update_message(
            message.chat.id,
            message.message_id,
            updates
        )
        
        # Обновляем в MongoDB
        existing = await mongo_storage.get_message(
            message.chat.id,
            message.message_id
        )
        if existing:
            existing.update(updates)
            await mongo_storage.save_message(existing)
        
        if config.DEBUG:
            print(f"✏️ Сообщение отредактировано: {message.chat.id}:{message.message_id}")
            
    except Exception as e:
        print(f"Ошибка обработки редактирования: {e}")

@router.message(Command("get_message"))
async def get_message_command(message: Message):
    """Получение информации о сообщении"""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /get_message <ID_сообщения>")
        return
    
    try:
        msg_id = int(args[1])
        msg_data = await redis_cache.get_message(message.chat.id, msg_id)
        
        if not msg_data:
            msg_data = await mongo_storage.get_message(message.chat.id, msg_id)
        
        if msg_data:
            response = f"📄 Сообщение ID: {msg_id}\n\n"
            response += f"👤 Пользователь: {msg_data.get('username', 'N/A')} ({msg_data.get('user_id', 'N/A')})\n"
            response += f"📅 Дата: {msg_data.get('created_at', 'N/A')}\n"
            
            if msg_data.get('is_edited'):
                response += f"✏️ Отредактировано: {msg_data.get('edited_at', 'N/A')}\n"
            
            if msg_data.get('is_deleted'):
                response += f"🗑️ Удалено: {msg_data.get('deleted_at', 'N/A')}\n"
            
            text = msg_data.get('text') or msg_data.get('caption') or '[медиа]'
            if len(text) > 200:
                text = text[:200] + "..."
            response += f"\nТекст:\n{text}"
            
            await message.answer(response)
        else:
            await message.answer("❌ Сообщение не найдено.")
            
    except ValueError:
        await message.answer("❌ Неверный ID сообщения.")
    except Exception as e:
        print(f"Ошибка команды get_message: {e}")
        await message.answer("❌ Произошла ошибка.")

@router.message(Command("deleted"))
async def get_deleted_command(message: Message):
    """Получение списка удаленных сообщений"""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return
    
    try:
        deleted = await redis_cache.get_deleted_messages(message.chat.id, limit=10)
        
        if not deleted:
            await message.answer("📭 Удаленных сообщений не найдено.")
            return
        
        response = "🗑️ Последние удаленные сообщения:\n\n"
        for i, msg in enumerate(deleted, 1):
            text = msg.get('text') or msg.get('caption') or '[медиа]'
            if len(text) > 50:
                text = text[:50] + "..."
            
            username = msg.get('username', msg.get('user_id', 'N/A'))
            response += f"{i}. ID: {msg.get('message_id')}\n"
            response += f"   👤 {username}\n"
            response += f"   📝 {text}\n\n"
        
        await message.answer(response)
        
    except Exception as e:
        print(f"Ошибка команды deleted: {e}")
        await message.answer("❌ Произошла ошибка.")

@router.message(Command("stats"))
async def get_stats_command(message: Message):
    """Получение статистики"""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет прав для этой команды.")
        return
    
    try:
        # Статистика Redis
        redis_stats = await redis_cache.get_stats()
        
        # Статистика чата
        chat_stats = await mongo_storage.get_chat_stats(message.chat.id)
        
        response = "📊 Статистика:\n\n"
        response += f"Сообщений в чате: {chat_stats.get('total_messages', 0)}\n"
        response += f"Удалено: {chat_stats.get('deleted_messages', 0)}\n"
        response += f"Отредактировано: {chat_stats.get('edited_messages', 0)}\n"
        
        if redis_stats:
            response += f"\nRedis:\n"
            response += f"Использование памяти: {redis_stats.get('used_memory', 'N/A')}\n"
            response += f"Подключения: {redis_stats.get('connected_clients', 0)}\n"
        
        await message.answer(response)
        
    except Exception as e:
        print(f"Ошибка команды stats: {e}")
        await message.answer("❌ Произошла ошибка.")
