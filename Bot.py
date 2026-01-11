import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib

from telegram import Update, Message, Chat
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackContext
)
from telegram.constants import MessageLimit

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MessageStatus(Enum):
    """Статусы сообщений"""
    ORIGINAL = "original"
    EDITED = "edited"
    DELETED = "deleted"

@dataclass
class CachedMessage:
    """Структура для кэширования сообщений"""
    message_id: int
    chat_id: int
    user_id: int
    text: Optional[str]
    caption: Optional[str]
    media_type: Optional[str]
    original_date: datetime
    edit_date: Optional[datetime]
    delete_date: Optional[datetime]
    status: MessageStatus
    forward_from: Optional[Dict[str, Any]] = None
    reply_to_message: Optional[Dict[str, Any]] = None
    entities: Optional[list] = None
    caption_entities: Optional[list] = None
    file_id: Optional[str] = None

class MessageCache:
    """Класс для кэширования сообщений"""
    
    def __init__(self):
        self.cache: Dict[str, CachedMessage] = {}
        self.deleted_messages: Dict[str, CachedMessage] = {}
        
    def _get_key(self, chat_id: int, message_id: int) -> str:
        """Генерация ключа для кэша"""
        return f"{chat_id}:{message_id}"
    
    def save_message(self, message: Message) -> str:
        """Сохранение сообщения в кэш"""
        key = self._get_key(message.chat_id, message.message_id)
        
        # Извлекаем информацию о медиа
        media_type, file_id = self._extract_media_info(message)
        
        # Извлекаем информацию о пересланном сообщении
        forward_info = self._extract_forward_info(message)
        
        # Извлекаем информацию о сообщении, на которое дан ответ
        reply_info = self._extract_reply_info(message)
        
        cached_message = CachedMessage(
            message_id=message.message_id,
            chat_id=message.chat_id,
            user_id=message.from_user.id if message.from_user else 0,
            text=message.text,
            caption=message.caption,
            media_type=media_type,
            original_date=message.date,
            edit_date=message.edit_date,
            delete_date=None,
            status=MessageStatus.ORIGINAL,
            forward_from=forward_info,
            reply_to_message=reply_info,
            entities=message.entities,
            caption_entities=message.caption_entities,
            file_id=file_id
        )
        
        self.cache[key] = cached_message
        logger.info(f"Сообщение сохранено в кэш: {key}")
        return key
    
    def update_message(self, message: Message) -> Optional[CachedMessage]:
        """Обновление сообщения (редактирование)"""
        key = self._get_key(message.chat_id, message.message_id)
        
        if key in self.cache:
            cached = self.cache[key]
            cached.text = message.text
            cached.caption = message.caption
            cached.edit_date = message.edit_date
            cached.status = MessageStatus.EDITED
            cached.entities = message.entities
            cached.caption_entities = message.caption_entities
            
            logger.info(f"Сообщение обновлено в кэше: {key}")
            return cached
        return None
    
    def mark_as_deleted(self, chat_id: int, message_id: int) -> Optional[CachedMessage]:
        """Пометка сообщения как удаленного"""
        key = self._get_key(chat_id, message_id)
        
        if key in self.cache:
            cached = self.cache[key]
            cached.delete_date = datetime.now()
            cached.status = MessageStatus.DELETED
            
            # Перемещаем в архив удаленных сообщений
            self.deleted_messages[key] = cached
            del self.cache[key]
            
            logger.info(f"Сообщение помечено как удаленное: {key}")
            return cached
        return None
    
    def get_message(self, chat_id: int, message_id: int) -> Optional[CachedMessage]:
        """Получение сообщения из кэша"""
        key = self._get_key(chat_id, message_id)
        return self.cache.get(key) or self.deleted_messages.get(key)
    
    def get_chat_history(self, chat_id: int, limit: int = 100) -> list[CachedMessage]:
        """Получение истории сообщений в чате"""
        chat_messages = []
        for key, message in list(self.cache.items()) + list(self.deleted_messages.items()):
            if message.chat_id == chat_id:
                chat_messages.append(message)
        
        # Сортируем по дате создания
        chat_messages.sort(key=lambda x: x.original_date, reverse=True)
        return chat_messages[:limit]
    
    def _extract_media_info(self, message: Message) -> tuple[Optional[str], Optional[str]]:
        """Извлечение информации о медиа"""
        if message.photo:
            return "photo", message.photo[-1].file_id if message.photo else None
        elif message.video:
            return "video", message.video.file_id
        elif message.audio:
            return "audio", message.audio.file_id
        elif message.document:
            return "document", message.document.file_id
        elif message.sticker:
            return "sticker", message.sticker.file_id
        elif message.voice:
            return "voice", message.voice.file_id
        elif message.video_note:
            return "video_note", message.video_note.file_id
        elif message.animation:
            return "animation", message.animation.file_id
        return None, None
    
    def _extract_forward_info(self, message: Message) -> Optional[Dict[str, Any]]:
        """Извлечение информации о пересылке"""
        if message.forward_from:
            return {
                'user_id': message.forward_from.id,
                'username': message.forward_from.username,
                'first_name': message.forward_from.first_name,
                'last_name': message.forward_from.last_name
            }
        elif message.forward_from_chat:
            return {
                'chat_id': message.forward_from_chat.id,
                'title': message.forward_from_chat.title,
                'username': message.forward_from_chat.username,
                'type': message.forward_from_chat.type
            }
        elif message.forward_sender_name:
            return {'sender_name': message.forward_sender_name}
        elif message.forward_from_message_id:
            return {'message_id': message.forward_from_message_id}
        return None
    
    def _extract_reply_info(self, message: Message) -> Optional[Dict[str, Any]]:
        """Извлечение информации о сообщении, на которое дан ответ"""
        if message.reply_to_message:
            return {
                'message_id': message.reply_to_message.message_id,
                'user_id': message.reply_to_message.from_user.id if message.reply_to_message.from_user else None,
                'text_preview': message.reply_to_message.text[:100] if message.reply_to_message.text else None
            }
        return None
    
    def save_to_file(self, filename: str = "message_cache.json"):
        """Сохранение кэша в файл"""
        data = {
            'cache': {k: asdict(v) for k, v in self.cache.items()},
            'deleted': {k: asdict(v) for k, v in self.deleted_messages.items()}
        }
        
        # Конвертация datetime в строки
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, default=convert_datetime, ensure_ascii=False, indent=2)
        
        logger.info(f"Кэш сохранен в файл: {filename}")
    
    def load_from_file(self, filename: str = "message_cache.json"):
        """Загрузка кэша из файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Восстановление объектов из словарей
            def dict_to_cached_message(d):
                if 'original_date' in d:
                    d['original_date'] = datetime.fromisoformat(d['original_date'])
                if 'edit_date' in d and d['edit_date']:
                    d['edit_date'] = datetime.fromisoformat(d['edit_date'])
                if 'delete_date' in d and d['delete_date']:
                    d['delete_date'] = datetime.fromisoformat(d['delete_date'])
                d['status'] = MessageStatus(d['status'])
                return CachedMessage(**d)
            
            self.cache = {k: dict_to_cached_message(v) for k, v in data.get('cache', {}).items()}
            self.deleted_messages = {k: dict_to_cached_message(v) for k, v in data.get('deleted', {}).items()}
            
            logger.info(f"Кэш загружен из файла: {filename}")
        except FileNotFoundError:
            logger.warning(f"Файл кэша не найден: {filename}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке кэша: {e}")

class MessageTrackerBot:
    """Основной класс бота"""
    
    def __init__(self, token: str):
        self.token = token
        self.cache = MessageCache()
        self.application = None
        
    async def start(self):
        """Запуск бота"""
        # Загрузка кэша из файла при старте
        self.cache.load_from_file()
        
        # Создание приложения
        self.application = Application.builder().token(self.token).build()
        
        # Добавление обработчиков
        self.application.add_handler(
            MessageHandler(filters.ALL & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(
            MessageHandler(filters.UpdateType.EDITED_MESSAGE, self.handle_edited_message)
        )
        self.application.add_handler(
            MessageHandler(filters.UpdateType.DELETED_MESSAGES, self.handle_deleted_messages)
        )
        
        # Обработчик для команды /get_deleted
        self.application.add_handler(
            MessageHandler(filters.COMMAND & filters.Regex("^/get_deleted"), self.get_deleted_messages)
        )
        
        # Обработчик для команды /get_message
        self.application.add_handler(
            MessageHandler(filters.COMMAND & filters.Regex("^/get_message"), self.get_specific_message)
        )
        
        # Сохранение кэша при остановке
        self.application.post_stop = self.save_cache_on_exit
        
        logger.info("Бот запущен и готов к работе")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка новых сообщений"""
        try:
            message = update.effective_message
            if message:
                self.cache.save_message(message)
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
    
    async def handle_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка отредактированных сообщений"""
        try:
            message = update.effective_message
            if message:
                cached = self.cache.update_message(message)
                if cached:
                    logger.info(f"Сообщение отредактировано: {message.chat_id}:{message.message_id}")
                    
                    # Можно уведомить администраторов об изменении
                    await self.notify_edition(message.chat_id, cached)
        except Exception as e:
            logger.error(f"Ошибка при обработке редактирования: {e}")
    
    async def handle_deleted_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка удаленных сообщений"""
        try:
            if update.deleted_messages:
                for message in update.deleted_messages:
                    cached = self.cache.mark_as_deleted(message.chat_id, message.message_id)
                    if cached:
                        logger.info(f"Сообщение удалено: {message.chat_id}:{message.message_id}")
                        
                        # Можно уведомить администраторов об удалении
                        await self.notify_deletion(message.chat_id, cached)
        except Exception as e:
            logger.error(f"Ошибка при обработке удаления: {e}")
    
    async def notify_edition(self, chat_id: int, cached_message: CachedMessage):
        """Уведомление об изменении сообщения (пример)"""
        # Здесь можно реализовать уведомление администраторов
        # или сохранение в специальный лог
        pass
    
    async def notify_deletion(self, chat_id: int, cached_message: CachedMessage):
        """Уведомление об удалении сообщения (пример)"""
        # Здесь можно реализовать уведомление администраторов
        # или сохранение в специальный лог
        pass
    
    async def get_deleted_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение списка удаленных сообщений (только для админов)"""
        try:
            message = update.effective_message
            chat_id = message.chat_id
            
            # Проверка прав администратора (упрощенно)
            # В реальном боте нужно проверять через bot.get_chat_administrators()
            
            deleted_messages = []
            for key, cached in self.cache.deleted_messages.items():
                if cached.chat_id == chat_id:
                    deleted_messages.append(cached)
            
            if not deleted_messages:
                await message.reply_text("Удаленных сообщений в этом чате не найдено.")
                return
            
            # Формируем ответ (первые 10 сообщений)
            response = "📋 Последние удаленные сообщения:\n\n"
            for i, msg in enumerate(deleted_messages[-10:], 1):
                text_preview = msg.text or msg.caption or "[медиа-сообщение]"
                if len(text_preview) > 50:
                    text_preview = text_preview[:50] + "..."
                
                response += f"{i}. ID: {msg.message_id}\n"
                response += f"   Пользователь: {msg.user_id}\n"
                response += f"   Текст: {text_preview}\n"
                response += f"   Удалено: {msg.delete_date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            await message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Ошибка при получении удаленных сообщений: {e}")
            await update.effective_message.reply_text("Произошла ошибка при получении данных.")
    
    async def get_specific_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение конкретного сообщения по ID"""
        try:
            message = update.effective_message
            args = context.args
            
            if not args or len(args) < 1:
                await message.reply_text("Использование: /get_message <ID_сообщения>")
                return
            
            message_id = int(args[0])
            cached = self.cache.get_message(message.chat_id, message_id)
            
            if not cached:
                await message.reply_text("Сообщение не найдено в кэше.")
                return
            
            response = f"📄 Информация о сообщении ID {message_id}:\n\n"
            response += f"Статус: {cached.status.value}\n"
            response += f"Пользователь: {cached.user_id}\n"
            response += f"Отправлено: {cached.original_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if cached.edit_date:
                response += f"Изменено: {cached.edit_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if cached.delete_date:
                response += f"Удалено: {cached.delete_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            response += f"\nТекст:\n{cached.text or cached.caption or '[нет текста]'}"
            
            if len(response) > MessageLimit.MAX_TEXT_LENGTH:
                response = response[:MessageLimit.MAX_TEXT_LENGTH - 100] + "..."
            
            await message.reply_text(response)
            
        except ValueError:
            await message.reply_text("Некорректный ID сообщения.")
        except Exception as e:
            logger.error(f"Ошибка при получении сообщения: {e}")
            await message.reply_text("Произошла ошибка при получении данных.")
    
    def save_cache_on_exit(self):
        """Сохранение кэша при выходе"""
        self.cache.save_to_file()
        logger.info("Кэш сохранен при выходе")

# Дополнительные функции для работы с кэшем
class CacheManager:
    """Менеджер для работы с кэшем сообщений"""
    
    @staticmethod
    def export_to_json(cache: MessageCache, filename: str = "export.json"):
        """Экспорт кэша в JSON"""
        cache.save_to_file(filename)
    
    @staticmethod
    def search_in_cache(cache: MessageCache, query: str, chat_id: Optional[int] = None) -> list[CachedMessage]:
        """Поиск в кэше по тексту"""
        results = []
        search_text = query.lower()
        
        for key, message in list(cache.cache.items()) + list(cache.deleted_messages.items()):
            if chat_id and message.chat_id != chat_id:
                continue
            
            text_to_search = (message.text or message.caption or "").lower()
            if search_text in text_to_search:
                results.append(message)
        
        return results
    
    @staticmethod
    def get_statistics(cache: MessageCache) -> Dict[str, Any]:
        """Получение статистики по кэшу"""
        total = len(cache.cache) + len(cache.deleted_messages)
        return {
            'total_messages': total,
            'active_messages': len(cache.cache),
            'deleted_messages': len(cache.deleted_messages),
            'edited_messages': len([m for m in cache.cache.values() if m.status == MessageStatus.EDITED]),
            'chats_count': len(set([m.chat_id for m in list(cache.cache.values()) + list(cache.deleted_messages.values())]))
        }

# Пример использования
async def main():
    # Получите токен у @BotFather
    TOKEN = "8512972061:AAEq_6oYrNgOZwlRmjpItqzptEkiJpxPKNs"
    
    # Создание и запуск бота
    bot = MessageTrackerBot(TOKEN)
    
    try:
        await bot.start()
        
        # Бесконечный цикл для работы бота
        while True:
            import asyncio
            await asyncio.sleep(3600)  # Спим 1 час
            
    except KeyboardInterrupt:
        print("\nБот остановлен")
    finally:
        if bot.application:
            await bot.application.stop()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())