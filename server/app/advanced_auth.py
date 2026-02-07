"""
Модуль улучшенной аутентификации для мессенджера
Содержит реализацию двухфакторной аутентификации и управления сессиями
"""
import pyotp
import secrets
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import hashlib
import base64
import os
from enum import Enum


class AuthTokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    TFA = "tfa"


class AdvancedAuthManager:
    """
    Класс для управления улучшенной аутентификацией
    """
    
    def __init__(self, db_pool, redis_client, jwt_secret: str, encryption_key: str):
        self.db_pool = db_pool
        self.redis = redis_client
        self.jwt_secret = jwt_secret
        self.encryption_key = encryption_key
        self.cipher_suite = Fernet(encryption_key)
        
        # Настройки безопасности
        self.access_token_ttl = timedelta(minutes=15)  # 15 минут
        self.refresh_token_ttl = timedelta(days=30)    # 30 дней
        self.tfa_token_ttl = timedelta(minutes=5)      # 5 минут
    
    async def register_user(self, username: str, password: str, email: str = None) -> Optional[Dict[str, Any]]:
        """
        Регистрация нового пользователя с возможностью включения 2FA
        """
        # Хешируем пароль
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        
        # Генерируем TFA secret
        tfa_secret = pyotp.random_base32()
        
        try:
            async with self.db_pool.acquire() as conn:
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
                'tfa_setup_required': True  # Пользователь должен настроить 2FA
            }
        except Exception as e:
            print(f"Ошибка регистрации пользователя: {e}")
            return None
    
    async def enable_2fa(self, user_id: int, verification_code: str) -> bool:
        """
        Включение двухфакторной аутентификации для пользователя
        """
        async with self.db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT tfa_secret FROM users WHERE id = $1",
                user_id
            )
        
        if not user_record or not user_record['tfa_secret']:
            return False
        
        totp = pyotp.TOTP(user_record['tfa_secret'])
        is_valid = totp.verify(verification_code, valid_window=1)
        
        if is_valid:
            # Включаем 2FA для пользователя
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET tfa_enabled = TRUE WHERE id = $1",
                    user_id
                )
        
        return is_valid
    
    async def disable_2fa(self, user_id: int, password: str) -> bool:
        """
        Отключение двухфакторной аутентификации (требует подтверждения паролем)
        """
        async with self.db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT password_hash FROM users WHERE id = $1",
                user_id
            )
        
        if not user_record or not bcrypt.checkpw(password.encode(), user_record['password_hash'].encode()):
            return False
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tfa_enabled = FALSE WHERE id = $1",
                user_id
            )
        
        return True
    
    async def generate_tfa_qr_code(self, user_id: int) -> Optional[str]:
        """
        Генерация QR-кода для настройки 2FA
        """
        async with self.db_pool.acquire() as conn:
            user_record = await conn.fetchrow(
                "SELECT username, tfa_secret FROM users WHERE id = $1",
                user_id
            )
        
        if not user_record or not user_record['tfa_secret']:
            return None
        
        totp_uri = pyotp.totp.TOTP(user_record['tfa_secret']).provisioning_uri(
            f"Мессенджер:{user_record['username']}",
            issuer_name="Мессенджер"
        )
        
        return totp_uri
    
    async def authenticate_user(self, username: str, password: str, 
                               tfa_code: str = None) -> Optional[Dict[str, Any]]:
        """
        Аутентификация пользователя с поддержкой 2FA
        """
        async with self.db_pool.acquire() as conn:
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
        access_token = self._create_token(
            user_id, AuthTokenType.ACCESS, self.access_token_ttl
        )
        refresh_token = self._create_token(
            user_id, AuthTokenType.REFRESH, self.refresh_token_ttl
        )
        
        # Сохраняем refresh token в Redis
        await self._store_refresh_token(user_id, refresh_token)
        
        return {
            'user_id': user_id,
            'username': user_record['username'],
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': self.access_token_ttl.total_seconds()
        }
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Обновление access токена с использованием refresh токена
        """
        try:
            # Декодируем refresh токен
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"])
            
            if payload.get('token_type') != AuthTokenType.REFRESH.value:
                return None
            
            user_id = payload.get('sub')
            if not user_id:
                return None
            
            # Проверяем, действителен ли refresh token в Redis
            stored_token = await self.redis.get(f"refresh_token:{user_id}")
            if stored_token != refresh_token:
                return None
            
            # Создаем новый access токен
            new_access_token = self._create_token(
                user_id, AuthTokenType.ACCESS, self.access_token_ttl
            )
            
            return {
                'access_token': new_access_token,
                'expires_in': self.access_token_ttl.total_seconds()
            }
        except jwt.ExpiredSignatureError:
            # Refresh токен истек, удаляем из Redis
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"], options={"verify_signature": False})
            user_id = payload.get('sub')
            if user_id:
                await self.redis.delete(f"refresh_token:{user_id}")
            return None
        except jwt.InvalidTokenError:
            return None
    
    async def logout_user(self, user_id: int, refresh_token: str = None) -> bool:
        """
        Выход пользователя, опционально с отзывом refresh токена
        """
        if refresh_token:
            # Проверяем, что refresh токен принадлежит пользователю
            try:
                payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=["HS256"])
                token_user_id = payload.get('sub')
                
                if token_user_id == user_id:
                    await self.redis.delete(f"refresh_token:{user_id}")
                    return True
            except jwt.InvalidTokenError:
                import logging
                logging.warning(f"Invalid refresh token provided during logout for user {user_id}")
                # Continue with logout process even if refresh token is invalid
                return False
        
        return False
    
    async def revoke_all_sessions(self, user_id: int) -> bool:
        """
        Отзыв всех сессий пользователя
        """
        # Удаляем refresh токен
        await self.redis.delete(f"refresh_token:{user_id}")
        
        # В реальной системе также нужно было бы управлять другими сессиями
        # через систему сессий пользователя
        
        return True
    
    def _create_token(self, user_id: int, token_type: AuthTokenType, 
                     expires_delta: timedelta) -> str:
        """
        Создание JWT токена
        """
        expire = datetime.utcnow() + expires_delta
        to_encode = {
            "sub": str(user_id),
            "token_type": token_type.value,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": secrets.token_urlsafe(16)  # JWT ID для предотвращения повторного использования
        }
        
        encoded_jwt = jwt.encode(to_encode, self.jwt_secret, algorithm="HS256")
        return encoded_jwt
    
    async def _store_refresh_token(self, user_id: int, refresh_token: str):
        """
        Сохранение refresh токена в Redis
        """
        # Сохраняем токен с TTL, соответствующим сроку действия
        ttl_seconds = self.refresh_token_ttl.total_seconds()
        await self.redis.setex(f"refresh_token:{user_id}", int(ttl_seconds), refresh_token)
    
    async def verify_token(self, token: str, expected_type: AuthTokenType = None) -> Optional[Dict[str, Any]]:
        """
        Проверка токена
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            if expected_type and payload.get('token_type') != expected_type.value:
                return None
            
            return {
                'user_id': int(payload.get('sub')),
                'token_type': payload.get('token_type'),
                'expires_at': payload.get('exp'),
                'issued_at': payload.get('iat'),
                'jti': payload.get('jti')
            }
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None


# Глобальный экземпляр для использования в приложении
# Инициализируется в основном приложении
advanced_auth_manager = None