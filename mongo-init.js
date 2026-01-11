// Инициализация MongoDB
db.createUser({
  user: "admin",
  pwd: "password", // Замените на ваш пароль из .env
  roles: [
    { role: "readWrite", db: "telegram_cache" },
    { role: "dbAdmin", db: "telegram_cache" }
  ]
});

db = db.getSiblingDB('telegram_cache');

// Создаем коллекции
db.createCollection('messages');
db.createCollection('events');
db.createCollection('audit_log');

// Создаем текстовый индекс для поиска
db.messages.createIndex({ 
  "text": "text", 
  "caption": "text" 
});
