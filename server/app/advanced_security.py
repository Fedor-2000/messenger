"""
Модуль улучшенной безопасности сессий для мессенджера
Содержит реализацию управления сессиями, рейт-лимитера и защиты от атак
"""
import secrets
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque
import asyncio
import ipaddress
from enum import Enum


class SessionStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPICIOUS = "suspicious"
    BLOCKED = "blocked"


class SessionSecurity:
    """
    Класс для управления безопасностью сессий
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.session_timeout = timedelta(hours=24)  # 24 часа бездействия
        self.max_concurrent_sessions = 5  # максимальное количество сессий
        self.device_fingerprint_timeout = timedelta(days=30)
        
        # Для рейт-лимитера
        self.rate_limit_windows = {
            'login_attempts': {'max_requests': 5, 'time_window': 300},  # 5 попыток за 5 минут
            'message_sending': {'max_requests': 10, 'time_window': 60},  # 10 сообщений в минуту
            'api_requests': {'max_requests': 100, 'time_window': 60},   # 100 запросов в минуту
        }
        
        # Для отслеживания подозрительной активности
        self.suspicious_activity_threshold = 3  # порог подозрительной активности
        self.block_duration = timedelta(hours=1)  # время блокировки
    
    async def create_secure_session(self, user_id: int, device_fingerprint: str, 
                                  ip_address: str, user_agent: str) -> Optional[str]:
        """
        Создание защищенной сессии с проверкой безопасности
        """
        # Проверяем количество активных сессий
        active_sessions = await self.get_user_sessions(user_id)
        if len(active_sessions) >= self.max_concurrent_sessions:
            # Проверяем, есть ли устаревшие сессии для удаления
            await self.cleanup_expired_sessions(user_id)
            active_sessions = await self.get_user_sessions(user_id)
            
            if len(active_sessions) >= self.max_concurrent_sessions:
                # Удаляем самую старую сессию
                oldest_session = min(active_sessions, key=lambda x: x['created_at'])
                await self.destroy_session(oldest_session['session_id'])
        
        # Проверяем подозрительную активность с этого IP
        if await self.is_ip_blocked(ip_address):
            return None
        
        # Хэшируем чувствительные данные для приватности
        device_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
        ua_hash = hashlib.sha256(user_agent.encode()).hexdigest()
        
        # Генерируем ID сессии
        session_id = secrets.token_urlsafe(32)
        
        session_data = {
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
            'device_hash': device_hash,
            'ip_hash': ip_hash,
            'user_agent_hash': ua_hash,
            'status': SessionStatus.ACTIVE.value,
            'activity_score': 0  # для отслеживания подозрительной активности
        }
        
        # Сохраняем сессию в Redis с TTL
        ttl_seconds = int(self.session_timeout.total_seconds())
        await self.redis.setex(
            f"session:{session_id}",
            ttl_seconds,
            str(session_data)
        )
        
        # Добавляем сессию к списку сессий пользователя
        await self.redis.sadd(f"user_sessions:{user_id}", session_id)
        
        # Обновляем время последней активности пользователя
        await self.redis.setex(
            f"user_last_activity:{user_id}",
            ttl_seconds,
            datetime.utcnow().isoformat()
        )
        
        return session_id
    
    async def validate_session(self, session_id: str, user_id: int, 
                             ip_address: str = None, user_agent: str = None) -> bool:
        """
        Проверка валидности сессии с учетом безопасности
        """
        session_data_str = await self.redis.get(f"session:{session_id}")
        if not session_data_str:
            return False
        
        try:
            # В реальности нужно десериализовать session_data_str
            # Для упрощения предполагаем, что это строка, представляющая словарь
            import ast
            session_data = ast.literal_eval(session_data_str)
        except Exception as e:
            import logging
            logging.error(f"Error parsing session data for {session_id}: {str(e)}")
            return False
        
        # Проверяем, соответствует ли user_id
        if str(session_data.get('user_id')) != str(user_id):
            return False
        
        # Проверяем статус сессии
        if session_data.get('status') == SessionStatus.BLOCKED.value:
            return False
        
        # Проверяем IP, если предоставлен
        if ip_address:
            expected_ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
            if session_data.get('ip_hash') != expected_ip_hash:
                # Возможно, подозрительная активность
                await self.increment_suspicious_activity(session_id, user_id)
                return False
        
        # Обновляем время последней активности
        session_data['last_activity'] = datetime.utcnow().isoformat()
        ttl = await self.redis.ttl(f"session:{session_id}")
        await self.redis.setex(
            f"session:{session_id}",
            ttl if ttl > 0 else int(self.session_timeout.total_seconds()),
            str(session_data)
        )
        
        # Обновляем время последней активности пользователя
        await self.redis.setex(
            f"user_last_activity:{user_id}",
            int(self.session_timeout.total_seconds()),
            datetime.utcnow().isoformat()
        )
        
        return True
    
    async def destroy_session(self, session_id: str) -> bool:
        """
        Уничтожение сессии
        """
        session_data_str = await self.redis.get(f"session:{session_id}")
        if not session_data_str:
            return False
        
        try:
            import ast
            session_data = ast.literal_eval(session_data_str)
            user_id = session_data.get('user_id')
        except Exception as e:
            import logging
            logging.error(f"Error parsing session data for {session_id}: {str(e)}")
            return False
        
        # Удаляем сессию
        await self.redis.delete(f"session:{session_id}")
        
        # Удаляем из списка сессий пользователя
        if user_id:
            await self.redis.srem(f"user_sessions:{user_id}", session_id)
        
        return True
    
    async def get_user_sessions(self, user_id: int) -> List[Dict]:
        """
        Получение всех сессий пользователя
        """
        session_ids = await self.redis.smembers(f"user_sessions:{user_id}")
        sessions = []
        
        for session_id in session_ids:
            session_data_str = await self.redis.get(f"session:{session_id}")
            if session_data_str:
                try:
                    import ast
                    session_data = ast.literal_eval(session_data_str)
                    sessions.append({
                        'session_id': session_id,
                        **session_data
                    })
                except Exception as e:
                    import logging
                    logging.error(f"Error parsing session data for {session_id}: {str(e)}")
                    continue
        
        return sessions
    
    async def cleanup_expired_sessions(self, user_id: int):
        """
        Очистка истекших сессий пользователя
        """
        session_ids = await self.redis.smembers(f"user_sessions:{user_id}")
        
        for session_id in session_ids.copy():  # copy() чтобы избежать изменения во время итерации
            ttl = await self.redis.ttl(f"session:{session_id}")
            if ttl == -1:  # TTL не установлен или сессия истекла
                await self.redis.delete(f"session:{session_id}")
                await self.redis.srem(f"user_sessions:{user_id}", session_id)
    
    async def is_rate_limited(self, identifier: str, action: str) -> bool:
        """
        Проверка рейт-лимита для действия
        """
        if action not in self.rate_limit_windows:
            return False
        
        config = self.rate_limit_windows[action]
        max_requests = config['max_requests']
        time_window = config['time_window']
        
        key = f"rate_limit:{action}:{identifier}"
        
        # Используем Redis для хранения запросов
        current_time = time.time()
        pipeline = self.redis.pipeline()
        
        # Удаляем старые записи
        pipeline.zremrangebyscore(key, 0, current_time - time_window)
        
        # Получаем количество текущих запросов
        pipeline.zcard(key)
        
        # Добавляем текущий запрос
        pipeline.zadd(key, {str(current_time): current_time})
        
        # Устанавливаем TTL для ключа
        pipeline.expire(key, time_window)
        
        results = await pipeline.execute()
        current_requests = results[1]
        
        return current_requests > max_requests
    
    async def increment_suspicious_activity(self, session_id: str, user_id: int):
        """
        Увеличение счетчика подозрительной активности
        """
        session_data_str = await self.redis.get(f"session:{session_id}")
        if not session_data_str:
            return
        
        try:
            import ast
            session_data = ast.literal_eval(session_data_str)
            activity_score = session_data.get('activity_score', 0)
            activity_score += 1
            
            session_data['activity_score'] = activity_score
            
            # Если порог превышен, помечаем сессию как подозрительную
            if activity_score >= self.suspicious_activity_threshold:
                session_data['status'] = SessionStatus.SUSPICIOUS.value
                
                # Также можем заблокировать пользователя на время
                await self.block_user_temporarily(user_id)
            
            ttl = await self.redis.ttl(f"session:{session_id}")
            await self.redis.setex(
                f"session:{session_id}",
                ttl if ttl > 0 else int(self.session_timeout.total_seconds()),
                str(session_data)
            )
        except Exception as e:
            # Log the error for debugging purposes
            import logging
            logging.error(f"Error updating session {session_id}: {str(e)}")
            # Continue execution without throwing the exception
            return False
    
    async def block_user_temporarily(self, user_id: int):
        """
        Временная блокировка пользователя
        """
        block_key = f"user_block:{user_id}"
        await self.redis.setex(
            block_key,
            int(self.block_duration.total_seconds()),
            "blocked"
        )
    
    async def is_user_blocked(self, user_id: int) -> bool:
        """
        Проверка, заблокирован ли пользователь
        """
        block_key = f"user_block:{user_id}"
        return await self.redis.exists(block_key) > 0
    
    async def is_ip_blocked(self, ip_address: str) -> bool:
        """
        Проверка, заблокирован ли IP-адрес
        """
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
        block_key = f"ip_block:{ip_hash}"
        return await self.redis.exists(block_key) > 0
    
    async def block_ip(self, ip_address: str, duration: timedelta = None):
        """
        Блокировка IP-адреса
        """
        if duration is None:
            duration = self.block_duration
            
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()
        block_key = f"ip_block:{ip_hash}"
        await self.redis.setex(
            block_key,
            int(duration.total_seconds()),
            "blocked"
        )
    
    async def generate_device_fingerprint(self, user_agent: str, ip_address: str, 
                                        screen_resolution: str = None) -> str:
        """
        Генерация отпечатка устройства для идентификации
        """
        fingerprint_data = f"{user_agent}|{ip_address}|{screen_resolution or ''}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    async def verify_device_fingerprint(self, session_id: str, current_fingerprint: str) -> bool:
        """
        Проверка соответствия отпечатка устройства
        """
        session_data_str = await self.redis.get(f"session:{session_id}")
        if not session_data_str:
            return False
        
        try:
            import ast
            session_data = ast.literal_eval(session_data_str)
            stored_fingerprint = session_data.get('device_hash')

            # Сравниваем хэши отпечатков
            current_hash = hashlib.sha256(current_fingerprint.encode()).hexdigest()
            return secrets.compare_digest(stored_fingerprint, current_hash)
        except Exception as e:
            import logging
            logging.error(f"Error validating device fingerprint for {session_id}: {str(e)}")
            return False
    
    async def log_security_event(self, user_id: int, event_type: str, 
                               details: Dict, severity: str = "medium"):
        """
        Логирование события безопасности
        """
        event = {
            'user_id': user_id,
            'event_type': event_type,
            'details': details,
            'severity': severity,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Сохраняем в Redis для дальнейшего анализа
        event_key = f"security_log:{user_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        await self.redis.lpush(event_key, str(event))
        
        # Устанавливаем TTL для логов
        await self.redis.expire(event_key, 60 * 60 * 24 * 30)  # 30 дней
        
        # Если событие высокого уровня важности, отправляем алерт
        if severity == "high":
            await self.send_security_alert(event)


    async def send_security_alert(self, event: Dict):
        """
        Отправка алерта о безопасности (в реальности через систему уведомлений)
        """
        # В реальном приложении здесь была бы отправка уведомления администратору
        print(f"SECURITY ALERT: {event}")


# Глобальный экземпляр для использования в приложении
session_security = SessionSecurity(None)