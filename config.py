import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Токен бота
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Настройки Redis для кэша
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    
    # MongoDB для персистентного хранения
    MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
    MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
    MONGO_DB = os.getenv("MONGO_DB", "telegram_cache")
    MONGO_USER = os.getenv("MONGO_USER")
    MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
    
    # Настройки кэша
    CACHE_TTL = int(os.getenv("CACHE_TTL", 86400))  # 24 часа
    MAX_MESSAGES_PER_CHAT = int(os.getenv("MAX_MESSAGES_PER_CHAT", 1000))
    
    # Список администраторов (ID пользователей Telegram)
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
    
    # Режим отладки
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # Настройки логирования
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @property
    def MONGO_URI(self):
        if self.MONGO_USER and self.MONGO_PASSWORD:
            return f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DB}?authSource=admin"
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DB}"
    
config = Config()
