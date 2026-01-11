import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import aioredis
from config import config

class RedisCache:
    """Менеджер Redis кэша"""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.connected = False
    
    async def connect(self):
        """Подключение к Redis"""
        try:
            self.redis = await aioredis.from_url(
                f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}",
                password=config.REDIS_PASSWORD,
                encoding="utf-8",
                decode_responses=True
            )
            self.connected = True
            print("✓ Redis подключен")
        except Exception as e:
            print(f"✗ Ошибка подключения к Redis: {e}")
            self.connected = False
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()
            self.connected = False
    
    def _get_message_key(self, chat_id: int, message_id: int) -> str:
        """Генерация ключа для сообщения"""
        return f"msg:{chat_id}:{message_id}"
    
    def _get_chat_key(self, chat_id: int) -> str:
        """Генерация ключа для списка сообщений чата"""
        return f"chat:{chat_id}:messages"
    
    def _get_deleted_key(self, chat_id: int) -> str:
        """Генерация ключа для удаленных сообщений"""
        return f"chat:{chat_id}:deleted"
    
    async def save_message(self, message_data: Dict[str, Any]) -> bool:
        """Сохранение сообщения в Redis"""
        if not self.connected or not self.redis:
            return False
        
        try:
            chat_id = message_data["chat_id"]
            message_id = message_data["message_id"]
            
            # Ключи
            msg_key = self._get_message_key(chat_id, message_id)
            chat_key = self._get_chat_key(chat_id)
            
            # Сохраняем сообщение
            await self.redis.setex(
                msg_key,
                config.CACHE_TTL,
                json.dumps(message_data, default=str)
            )
            
            # Добавляем в список сообщений чата
            await self.redis.zadd(chat_key, {str(message_id): message_id})
            
            # Ограничиваем размер списка
            await self.redis.zremrangebyrank(
                chat_key, 
                0, 
                -config.MAX_MESSAGES_PER_CHAT - 1
            )
            
            return True
        except Exception as e:
            print(f"Ошибка сохранения в Redis: {e}")
            return False
    
    async def update_message(self, chat_id: int, message_id: int, 
                           updates: Dict[str, Any]) -> bool:
        """Обновление сообщения"""
        if not self.connected or not self.redis:
            return False
        
        try:
            msg_key = self._get_message_key(chat_id, message_id)
            existing = await self.redis.get(msg_key)
            
            if existing:
                data = json.loads(existing)
                data.update(updates)
                data["edited_at"] = datetime.now().isoformat()
                data["is_edited"] = True
                
                await self.redis.setex(
                    msg_key,
                    config.CACHE_TTL,
                    json.dumps(data, default=str)
                )
                return True
            return False
        except Exception as e:
            print(f"Ошибка обновления в Redis: {e}")
            return False
    
    async def mark_as_deleted(self, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """Пометка сообщения как удаленного"""
        if not self.connected or not self.redis:
            return None
        
        try:
            msg_key = self._get_message_key(chat_id, message_id)
            deleted_key = self._get_deleted_key(chat_id)
            
            # Получаем сообщение
            message_data = await self.redis.get(msg_key)
            if not message_data:
                return None
            
            data = json.loads(message_data)
            data["deleted_at"] = datetime.now().isoformat()
            data["is_deleted"] = True
            
            # Сохраняем в список удаленных
            await self.redis.zadd(deleted_key, {str(message_id): message_id})
            
            # Удаляем из основного кэша
            await self.redis.delete(msg_key)
            
            # Сохраняем удаленное сообщение
            deleted_msg_key = f"deleted:{msg_key}"
            await self.redis.setex(
                deleted_msg_key,
                config.CACHE_TTL * 7,  # Храним удаленные дольше
                json.dumps(data, default=str)
            )
            
            return data
        except Exception as e:
            print(f"Ошибка пометки удаления: {e}")
            return None
    
    async def get_message(self, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """Получение сообщения"""
        if not self.connected or not self.redis:
            return None
        
        try:
            # Сначала ищем в активных
            msg_key = self._get_message_key(chat_id, message_id)
            message_data = await self.redis.get(msg_key)
            
            # Если не нашли, ищем в удаленных
            if not message_data:
                deleted_msg_key = f"deleted:{msg_key}"
                message_data = await self.redis.get(deleted_msg_key)
            
            return json.loads(message_data) if message_data else None
        except Exception as e:
            print(f"Ошибка получения из Redis: {e}")
            return None
    
    async def get_chat_messages(self, chat_id: int, 
                               limit: int = 50,
                               offset: int = 0) -> List[Dict[str, Any]]:
        """Получение сообщений чата"""
        if not self.connected or not self.redis:
            return []
        
        try:
            chat_key = self._get_chat_key(chat_id)
            message_ids = await self.redis.zrevrange(
                chat_key, offset, offset + limit - 1
            )
            
            messages = []
            for msg_id in message_ids:
                msg_key = self._get_message_key(chat_id, int(msg_id))
                message_data = await self.redis.get(msg_key)
                if message_data:
                    messages.append(json.loads(message_data))
            
            return messages
        except Exception as e:
            print(f"Ошибка получения сообщений чата: {e}")
            return []
    
    async def get_deleted_messages(self, chat_id: int,
                                 limit: int = 50) -> List[Dict[str, Any]]:
        """Получение удаленных сообщений"""
        if not self.connected or not self.redis:
            return []
        
        try:
            deleted_key = self._get_deleted_key(chat_id)
            message_ids = await self.redis.zrevrange(
                deleted_key, 0, limit - 1
            )
            
            messages = []
            for msg_id in message_ids:
                msg_key = f"deleted:msg:{chat_id}:{msg_id}"
                message_data = await self.redis.get(msg_key)
                if message_data:
                    messages.append(json.loads(message_data))
            
            return messages
        except Exception as e:
            print(f"Ошибка получения удаленных сообщений: {e}")
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики Redis"""
        if not self.connected or not self.redis:
            return {}
        
        try:
            info = await self.redis.info()
            return {
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "total_connections": info.get("total_connections_received", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            print(f"Ошибка получения статистики Redis: {e}")
            return {}

redis_cache = RedisCache()
