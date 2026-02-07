# Authentication Microservice
# File: services/auth_microservice/main.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import bcrypt
import jwt
import aiohttp
from aiohttp import web
import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class TokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    VERIFICATION = "verification"

class AuthRequest(BaseModel):
    username: str
    password: str
    tfa_code: Optional[str] = None
    device_fingerprint: Optional[str] = None

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    username: str
    session_id: str

class AuthService:
    def __init__(self):
        self.jwt_secret = "your-super-secret-jwt-key-change-it"
        self.token_expiry = {
            TokenType.ACCESS: timedelta(minutes=15),
            TokenType.REFRESH: timedelta(days=30),
            TokenType.VERIFICATION: timedelta(hours=24)
        }
        # Устанавливаем глобальные переменные из основного приложения
        global db_pool, redis_client
        self.db_pool = db_pool
        self.redis_client = redis_client

    async def authenticate_user(self, username: str, password: str, 
                               tfa_code: Optional[str] = None) -> Optional[AuthResponse]:
        """Аутентификация пользователя"""
        # Получаем пользователя из базы данных
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                """
                SELECT id, username, password_hash, tfa_enabled, tfa_secret
                FROM users WHERE username = $1
                """,
                username
            )

        if not user:
            return None

        # Проверяем пароль
        if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
            return None

        # Если включена 2FA, проверяем код
        if user['tfa_enabled'] and tfa_code:
            if not await self._verify_2fa_code(user['tfa_secret'], tfa_code):
                return None

        # Создаем токены
        user_id = user['id']
        access_token = self._create_token(user_id, TokenType.ACCESS)
        refresh_token = self._create_token(user_id, TokenType.REFRESH)

        # Создаем сессию
        session_id = await self._create_user_session(user_id)

        # Обновляем время последнего входа
        await self._update_last_login(user_id)

        response = AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.token_expiry[TokenType.ACCESS].total_seconds()),
            user_id=user_id,
            username=user['username'],
            session_id=session_id
        )

        # Логируем аутентификацию
        await self._log_authentication(user_id, "success")

        return response

    def _create_token(self, user_id: int, token_type: TokenType) -> str:
        """Создание JWT токена"""
        expiry = datetime.utcnow() + self.token_expiry[token_type]
        payload = {
            "sub": str(user_id),
            "type": token_type.value,
            "exp": expiry,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4())  # JWT ID для предотвращения повторного использования
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        return token

    async def _create_user_session(self, user_id: int) -> str:
        """Создание пользовательской сессии"""
        session_id = str(uuid.uuid4())
        session_data = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat()
        }

        # Сохраняем сессию в Redis
        await self.redis_client.setex(
            f"session:{session_id}",
            int(self.token_expiry[TokenType.REFRESH].total_seconds()),
            json.dumps(session_data)
        )

        # Добавляем сессию к пользователю
        await self.redis_client.sadd(f"user_sessions:{user_id}", session_id)

        return session_id

    async def _update_last_login(self, user_id: int):
        """Обновление времени последнего входа"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login = $1 WHERE id = $2",
                datetime.utcnow(), user_id
            )

    async def _verify_2fa_code(self, secret: str, code: str) -> bool:
        """Проверка кода двухфакторной аутентификации"""
        # Используем pyotp для проверки кода
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    async def _log_authentication(self, user_id: int, status: str):
        """Логирование попытки аутентификации"""
        log_entry = {
            "user_id": user_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "auth_service"
        }

        # Сохраняем в Redis для быстрого доступа
        await self.redis_client.lpush("auth_logs", json.dumps(log_entry))
        await self.redis_client.ltrim("auth_logs", 0, 999)  # Храним последние 1000 записей

    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Обновление access токена с помощью refresh токена"""
        try:
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"])
            
            if payload.get("type") != TokenType.REFRESH.value:
                return None

            user_id = int(payload.get("sub"))
            if not user_id:
                return None

            # Проверяем, действителен ли refresh токен
            jti = payload.get("jti")
            if await self._is_token_revoked(jti):
                return None

            # Создаем новый access токен
            new_access_token = self._create_token(user_id, TokenType.ACCESS)

            return {
                "access_token": new_access_token,
                "token_type": "bearer",
                "expires_in": int(self.token_expiry[TokenType.ACCESS].total_seconds())
            }
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def _is_token_revoked(self, jti: str) -> bool:
        """Проверка, отозван ли токен"""
        if not jti:
            return False
        revoked = await self.redis_client.get(f"revoked_token:{jti}")
        return revoked is not None

    async def logout_user(self, session_id: str, user_id: int) -> bool:
        """Выход пользователя из системы"""
        # Помечаем сессию как завершенную
        await self.redis_client.delete(f"session:{session_id}")

        # Удаляем из списка сессий пользователя
        await self.redis_client.srem(f"user_sessions:{user_id}", session_id)

        # Добавляем токен в черный список
        await self._revoke_refresh_token(session_id)
        
        return True

    async def _revoke_refresh_token(self, session_id: str):
        """Отзыв refresh токена"""
        # В реальной системе здесь будет более сложная логика отзыва токенов
        logger.info(f"Revoking refresh token for session {session_id}")
        # Добавляем токен в черный список
        token_jti = f"session_{session_id}"
        await redis_client.setex(
            f"revoked_token:{token_jti}",
            int(self.token_expiry[TokenType.REFRESH].total_seconds()),
            "revoked"
        )
        return True

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Проверка токена"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            # Проверяем, не отозван ли токен
            jti = payload.get("jti")
            if await self._is_token_revoked(jti):
                return None

            return {
                "user_id": int(payload.get("sub")),
                "token_type": payload.get("type"),
                "exp": payload.get("exp"),
                "iat": payload.get("iat")
            }
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

# Инициализация сервиса
auth_service = AuthService()

# Установка глобальных переменных
async def set_global_vars(db_pool_param, redis_client_param):
    """Установка глобальных переменных для сервиса"""
    global db_pool, redis_client
    db_pool = db_pool_param
    redis_client = redis_client_param
    auth_service.db_pool = db_pool_param
    auth_service.redis_client = redis_client_param

async def auth_handler(request):
    """Обработчик аутентификации"""
    data = await request.json()
    
    auth_request = AuthRequest(**data)
    
    response = await auth_service.authenticate_user(
        auth_request.username,
        auth_request.password,
        auth_request.tfa_code
    )
    
    if response:
        return web.json_response(response.dict())
    else:
        return web.json_response({"error": "Invalid credentials"}, status=401)

async def refresh_handler(request):
    """Обработчик обновления токена"""
    data = await request.json()
    refresh_token = data.get("refresh_token")
    
    if not refresh_token:
        return web.json_response({"error": "Refresh token required"}, status=400)
    
    result = await auth_service.refresh_access_token(refresh_token)
    
    if result:
        return web.json_response(result)
    else:
        return web.json_response({"error": "Invalid refresh token"}, status=401)

async def logout_handler(request):
    """Обработчик выхода"""
    data = await request.json()
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    
    if not session_id or not user_id:
        return web.json_response({"error": "Session ID and User ID required"}, status=400)
    
    success = await auth_service.logout_user(session_id, user_id)
    
    if success:
        return web.json_response({"status": "logged_out"})
    else:
        return web.json_response({"error": "Logout failed"}, status=500)

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({"status": "healthy", "service": "auth"})

async def initialize_db():
    """Инициализация базы данных"""
    global db_pool
    db_pool = await asyncpg.create_pool(
        "postgresql://messenger:password@db:5432/messenger",
        min_size=5,
        max_size=20
    )

async def initialize_redis():
    """Инициализация Redis"""
    global redis_client
    redis_client = redis.from_url("redis://redis:6379", decode_responses=True)

async def init_app():
    """Инициализация приложения"""
    await initialize_db()
    await initialize_redis()
    
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/auth', auth_handler)
    app.router.add_post('/refresh', refresh_handler)
    app.router.add_post('/logout', logout_handler)
    app.router.add_get('/health', health_check)
    
    return app

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = loop.run_until_complete(init_app())
    
    web.run_app(app, host='0.0.0.0', port=8000)