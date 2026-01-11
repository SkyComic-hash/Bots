from typing import Optional, Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from config import config

class MongoStorage:
    """Персистентное хранение в MongoDB"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.connected = False
    
    async def connect(self):
        """Подключение к MongoDB"""
        try:
            self.client = AsyncIOMotorClient(config.MONGO_URI)
            self.db = self.client[config.MONGO_DB]
            
            # Создаем индексы
            await self.db.messages.create_index([("chat_id", 1), ("message_id", 1)], unique=True)
            await self.db.messages.create_index([("created_at", -1)])
            await self.db.messages.create_index([("is_deleted", 1)])
            await self.db.messages.create_index([("user_id", 1)])
            
            self.connected = True
            print("✓ MongoDB подключена")
        except Exception as e:
            print(f"✗ Ошибка подключения к MongoDB: {e}")
            self.connected = False
    
    async def disconnect(self):
        """Отключение от MongoDB"""
        if self.client:
            self.client.close()
            self.connected = False
    
    async def save_message(self, message_data: Dict[str, Any]) -> bool:
        """Сохранение сообщения в MongoDB"""
        if not self.connected:
            return False
        
        try:
            message_data["_id"] = f"{message_data['chat_id']}:{message_data['message_id']}"
            message_data["created_at"] = datetime.now()
            
            await self.db.messages.update_one(
                {"_id": message_data["_id"]},
                {"$set": message_data},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Ошибка сохранения в MongoDB: {e}")
            return False
    
    async def get_message(self, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """Получение сообщения из MongoDB"""
        if not self.connected:
            return None
        
        try:
            doc_id = f"{chat_id}:{message_id}"
            message = await self.db.messages.find_one({"_id": doc_id})
            if message:
                message.pop('_id', None)
            return message
        except Exception as e:
            print(f"Ошибка получения из MongoDB: {e}")
            return None
    
    async def search_messages(self, chat_id: Optional[int] = None,
                            user_id: Optional[int] = None,
                            text: Optional[str] = None,
                            is_deleted: Optional[bool] = None,
                            limit: int = 100) -> List[Dict[str, Any]]:
        """Поиск сообщений в MongoDB"""
        if not self.connected:
            return []
        
        try:
            query = {}
            if chat_id:
                query["chat_id"] = chat_id
            if user_id:
                query["user_id"] = user_id
            if text:
                query["$text"] = {"$search": text}
            if is_deleted is not None:
                query["is_deleted"] = is_deleted
            
            cursor = self.db.messages.find(query).sort("created_at", -1).limit(limit)
            messages = await cursor.to_list(length=limit)
            
            # Убираем _id
            for msg in messages:
                msg.pop('_id', None)
            
            return messages
        except Exception as e:
            print(f"Ошибка поиска в MongoDB: {e}")
            return []
    
    async def get_chat_stats(self, chat_id: int) -> Dict[str, Any]:
        """Статистика по чату"""
        if not self.connected:
            return {}
        
        try:
            total = await self.db.messages.count_documents({"chat_id": chat_id})
            deleted = await self.db.messages.count_documents({
                "chat_id": chat_id,
                "is_deleted": True
            })
            edited = await self.db.messages.count_documents({
                "chat_id": chat_id,
                "is_edited": True
            })
            
            # Самый активный пользователь
            pipeline = [
                {"$match": {"chat_id": chat_id}},
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 1}
            ]
            
            result = await self.db.messages.aggregate(pipeline).to_list(1)
            top_user = result[0] if result else None
            
            return {
                "total_messages": total,
                "deleted_messages": deleted,
                "edited_messages": edited,
                "top_user": top_user
            }
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return {}

mongo_storage = MongoStorage()
