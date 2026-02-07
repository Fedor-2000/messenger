# Auth Service
# File: services/auth_service/main.py

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import aiohttp
from aiohttp import web
import jwt
import bcrypt
from cryptography.fernet import Fernet
import pyotp
import asyncpg
import redis.asyncio as redis

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-it')
    DB_URL = os.getenv('DB_URL', 'postgresql://messenger:password@db:5432/messenger')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')

config = Config()

# Глобальные переменные
db_pool = None
redis_client = None

class AuthService:
    def __init__(self):
        self.jwt_secret = config.JWT_SECRET

    async def register_user(self, username: str, password: str, email: str = None) -> Optional[Dict]:
        """Регистрация нового пользователя"""
        try:
            # Хешируем пароль
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            
            # Генерируем TFA secret
            tfa_secret = pyotp.random_base32()
            
            async with db_pool.acquire() as conn:
                # Проверяем, существует ли пользователь
                existing_user = await conn.fetchrow(
                    "SELECT id FROM users WHERE username = $1",
                    username
                )
                
                if existing_user:
                    return None
                
                # Создаем пользователя
                user_record = await conn.fetchrow(
                    """
                    INSERT INTO users (
                        username, password_hash, email, tfa_secret, created_at
                    ) VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, username, created_at
                    """,
                    username, password_hash, email, tfa_secret, datetime.utcnow()
                )
            
            return {
                'user_id': user_record['id'],
                'username': user_record['username'],
                'created_at': user_record['created_at'],
                'tfa_setup_required': True
            }
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя: {e}")
            return None

    async def authenticate_user(self, username: str, password: str, tfa_code: str = None) -> Optional[Dict]:
        """Аутентификация пользователя"""
        async with db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                """
                SELECT id, username, password_hash, tfa_enabled, tfa_secret 
                FROM users WHERE username = $1
                """,
                username
            )
        
        if not user_record:
            return None
        
        # Проверяем пароль
        if not bcrypt.checkpw(password.encode(), user_record['password_hash'].encode()):
            return None
        
        user_id = user_record['id']
        tfa_enabled = user_record['tfa_enabled']
        
        # Если включена 2FA, проверяем код
        if tfa_enabled:
            if not tfa_code or not user_record['tfa_secret']:
                return None
            
            totp = pyotp.TOTP(user_record['tfa_secret'])
            if not totp.verify(tfa_code, valid_window=1):
                return None
        
        # Создаем токены
        access_token = self._create_token(user_id, "access", timedelta(minutes=15))
        refresh_token = self._create_token(user_id, "refresh", timedelta(days=30))
        
        # Сохраняем refresh token в Redis
        await redis_client.setex(f"refresh_token:{user_id}", 30*24*60*60, refresh_token)
        
        return {
            'user_id': user_id,
            'username': user_record['username'],
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': 15*60
        }

    def _create_token(self, user_id: int, token_type: str, expires_delta: timedelta) -> str:
        """Создание JWT токена"""
        expire = datetime.utcnow() + expires_delta
        to_encode = {
            "sub": str(user_id),
            "token_type": token_type,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        encoded_jwt = jwt.encode(to_encode, self.jwt_secret, algorithm="HS256")
        return encoded_jwt

    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict]:
        """Обновление access токена"""
        try:
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"])
            
            if payload.get('token_type') != 'refresh':
                return None
            
            user_id = payload.get('sub')
            if not user_id:
                return None
            
            # Проверяем, действителен ли refresh token в Redis
            stored_token = await redis_client.get(f"refresh_token:{user_id}")
            if stored_token != refresh_token:
                return None
            
            # Создаем новый access токен
            new_access_token = self._create_token(user_id, "access", timedelta(minutes=15))
            
            return {
                'access_token': new_access_token,
                'expires_in': 15*60
            }
        except jwt.ExpiredSignatureError:
            # Refresh токен истек, удаляем из Redis
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"], options={"verify_signature": False})
            user_id = payload.get('sub')
            if user_id:
                await redis_client.delete(f"refresh_token:{user_id}")
            return None
        except jwt.InvalidTokenError:
            return None

# Инициализация сервиса
auth_service = AuthService()

async def register_handler(request):
    """Обработчик регистрации"""
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    result = await auth_service.register_user(username, password, email)
    
    if result:
        return web.json_response(result, status=201)
    else:
        return web.json_response({'error': 'Registration failed'}, status=400)

async def login_handler(request):
    """Обработчик входа"""
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    tfa_code = data.get('tfa_code')
    
    result = await auth_service.authenticate_user(username, password, tfa_code)
    
    if result:
        return web.json_response(result)
    else:
        return web.json_response({'error': 'Invalid credentials'}, status=401)

async def refresh_handler(request):
    """Обработчик обновления токена"""
    data = await request.json()
    refresh_token = data.get('refresh_token')
    
    result = await auth_service.refresh_access_token(refresh_token)
    
    if result:
        return web.json_response(result)
    else:
        return web.json_response({'error': 'Invalid refresh token'}, status=401)

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({'status': 'healthy'})

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/register', register_handler)
    app.router.add_post('/login', login_handler)
    app.router.add_post('/refresh', refresh_handler)
    app.router.add_get('/health', health_check)
    
    return app

async def init_db():
    """Инициализация базы данных"""
    global db_pool
    db_pool = await asyncpg.create_pool(config.DB_URL, min_size=5, max_size=20)

async def init_redis():
    """Инициализация Redis"""
    global redis_client
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)

async def main():
    """Основная функция запуска"""
    await init_db()
    await init_redis()
    
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    
    logger.info("Auth Service запущен на порту 8000")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())