# server/app/additional_services.py
import asyncio
import aiohttp
import aioredis
import asyncpg
from typing import Dict, List, Any, Optional, Callable
import logging
import json
import time
from datetime import datetime, timedelta
import uuid
from enum import Enum
import re
from dataclasses import dataclass
from abc import ABC, abstractmethod
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
import jwt
from PIL import Image
import io
import boto3
from botocore.exceptions import ClientError
import openai
from transformers import pipeline, AutoTokenizer, AutoModel
import torch
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

class ServiceType(Enum):
    NOTIFICATION = "notification"
    ANALYTICS = "analytics"
    MODERATION = "moderation"
    TRANSLATION = "translation"
    AI_ASSISTANT = "ai_assistant"
    BACKUP = "backup"
    MONITORING = "monitoring"
    SPAM_DETECTION = "spam_detection"
    CONTENT_FILTER = "content_filter"
    VOICE_PROCESSING = "voice_processing"

@dataclass
class Notification:
    id: str
    user_id: int
    title: str
    message: str
    type: str  # info, warning, error, success
    created_at: datetime
    read: bool = False
    priority: int = 1  # 1-5, 5 highest

@dataclass
class AnalyticsEvent:
    id: str
    user_id: int
    event_type: str
    properties: Dict[str, Any]
    timestamp: datetime
    session_id: str

class NotificationService:
    """Сервис уведомлений"""
    
    def __init__(self, redis_client, db_pool):
        self.redis = redis_client
        self.db_pool = db_pool
        self.push_service = None  # APNs, FCM, etc.
    
    async def send_push_notification(self, user_id: int, title: str, message: str, 
                                   priority: int = 1, data: Optional[Dict] = None):
        """Отправка push-уведомления"""
        notification = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            message=message,
            type="push",
            created_at=datetime.utcnow(),
            priority=priority
        )
        
        # Сохраняем в базу
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notifications (id, user_id, title, message, type, created_at, priority)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                notification.id, notification.user_id, notification.title,
                notification.message, notification.type, notification.created_at,
                notification.priority
            )
        
        # Отправляем в Redis для немедленной доставки
        notification_data = {
            'id': notification.id,
            'user_id': user_id,
            'title': title,
            'message': message,
            'priority': priority,
            'timestamp': notification.created_at.isoformat()
        }
        
        await self.redis.publish(f"user:{user_id}:notifications", json.dumps(notification_data))
        
        # Отправляем push-уведомление если пользователь онлайн
        is_online = await self.redis.get(f"user:{user_id}:online")
        if is_online:
            await self._send_immediate_notification(user_id, notification_data)
    
    async def _send_immediate_notification(self, user_id: int, notification_data: Dict):
        """Отправка немедленного уведомления"""
        # В реальном приложении здесь будет интеграция с APNs/FCM
        # Для упрощения логируем уведомление
        import logging
        logging.info(f"Immediate notification for user {user_id}: {notification_data}")
        # В реальном приложении: await self.push_notification_service.send(user_id, notification_data)
        return True
    
    async def send_email_notification(self, user_id: int, subject: str, body: str):
        """Отправка email-уведомления"""
        # Используем централизованную функцию отправки email с сервера
        from .main import send_email_notification as server_send_email
        return await server_send_email(user_id, subject, body)
    
    async def get_user_notifications(self, user_id: int, limit: int = 50, 
                                   offset: int = 0, unread_only: bool = False):
        """Получение уведомлений пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2
        
        if unread_only:
            conditions.append(f"read = FALSE")
        
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, user_id, title, message, type, created_at, read, priority
            FROM notifications
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        params.extend([limit, offset])
        
        async with self.db_pool.acquire() as conn:
            results = await conn.fetch(query, *params)
        
        return [Notification(
            id=row['id'],
            user_id=row['user_id'],
            title=row['title'],
            message=row['message'],
            type=row['type'],
            created_at=row['created_at'],
            read=row['read'],
            priority=row['priority']
        ) for row in results]
    
    async def mark_as_read(self, notification_id: str, user_id: int):
        """Отметка уведомления как прочитанного"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE notifications SET read = TRUE WHERE id = $1 AND user_id = $2",
                notification_id, user_id
            )

class AnalyticsService:
    """Сервис аналитики"""
    
    def __init__(self, redis_client, db_pool):
        self.redis = redis_client
        self.db_pool = db_pool
        self.event_buffer = []
        self.buffer_size = 100
        self.flush_interval = 5  # seconds
    
    async def track_event(self, user_id: int, event_type: str, 
                         properties: Optional[Dict] = None, session_id: Optional[str] = None):
        """Отслеживание события"""
        event = AnalyticsEvent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=event_type,
            properties=properties or {},
            timestamp=datetime.utcnow(),
            session_id=session_id or str(uuid.uuid4())
        )
        
        # Добавляем в буфер
        self.event_buffer.append(event)
        
        # Если буфер полон, сбрасываем
        if len(self.event_buffer) >= self.buffer_size:
            await self.flush_events()
    
    async def flush_events(self):
        """Сброс событий в базу данных"""
        if not self.event_buffer:
            return
        
        events_to_save = self.event_buffer[:self.buffer_size]
        self.event_buffer = self.event_buffer[self.buffer_size:]
        
        async with self.db_pool.acquire() as conn:
            # Массовая вставка событий
            values = [
                (event.id, event.user_id, event.event_type, 
                 json.dumps(event.properties), event.timestamp, event.session_id)
                for event in events_to_save
            ]
            
            await conn.executemany(
                """
                INSERT INTO analytics_events (id, user_id, event_type, properties, timestamp, session_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                values
            )
    
    async def get_user_engagement(self, user_id: int, days: int = 30):
        """Получение метрик вовлеченности пользователя"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with self.db_pool.acquire() as conn:
            # Количество сессий
            session_count = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT session_id) 
                FROM analytics_events 
                WHERE user_id = $1 AND timestamp >= $2
                """,
                user_id, start_date
            )
            
            # Количество событий
            event_count = await conn.fetchval(
                """
                SELECT COUNT(*) 
                FROM analytics_events 
                WHERE user_id = $1 AND timestamp >= $2
                """,
                user_id, start_date
            )
            
            # Последняя активность
            last_activity = await conn.fetchval(
                """
                SELECT MAX(timestamp) 
                FROM analytics_events 
                WHERE user_id = $1
                """,
                user_id
            )
        
        return {
            'session_count': session_count or 0,
            'event_count': event_count or 0,
            'last_activity': last_activity.isoformat() if last_activity else None,
            'days': days
        }
    
    async def get_daily_active_users(self, days: int = 30):
        """Получение DAU (Daily Active Users)"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with self.db_pool.acquire() as conn:
            dau_data = await conn.fetch(
                """
                SELECT DATE(timestamp) as day, COUNT(DISTINCT user_id) as dau
                FROM analytics_events
                WHERE timestamp >= $1
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
                """,
                start_date
            )
        
        return [(row['day'].isoformat(), row['dau']) for row in dau_data]

class ContentModerationService:
    """Сервис модерации контента"""
    
    def __init__(self):
        self.bad_words = set()
        self.spam_patterns = []
        self.image_moderation_enabled = True
        self.text_moderation_enabled = True
        self.auto_ban_threshold = 5  # количество нарушений для бана
    
    def load_bad_words(self, bad_words_list: List[str]):
        """Загрузка списка запрещенных слов"""
        self.bad_words = set(word.lower() for word in bad_words_list)
    
    def add_spam_pattern(self, pattern: str):
        """Добавление паттерна спама"""
        self.spam_patterns.append(re.compile(pattern, re.IGNORECASE))
    
    async def moderate_text(self, text: str, user_id: int = None) -> Dict[str, Any]:
        """Модерация текста"""
        result = {
            'is_safe': True,
            'violations': [],
            'severity': 'low',  # low, medium, high
            'auto_action': None  # warn, mute, ban
        }
        
        if not self.text_moderation_enabled:
            return result
        
        text_lower = text.lower()
        
        # Проверка на запрещенные слова
        violations = []
        for word in self.bad_words:
            if word in text_lower:
                violations.append({
                    'type': 'bad_word',
                    'word': word,
                    'severity': 'medium'
                })
        
        # Проверка на спам паттерны
        for pattern in self.spam_patterns:
            if pattern.search(text):
                violations.append({
                    'type': 'spam_pattern',
                    'pattern': pattern.pattern,
                    'severity': 'high'
                })
        
        if violations:
            result['is_safe'] = False
            result['violations'] = violations
            
            # Определяем максимальный уровень серьезности
            severities = [v['severity'] for v in violations]
            if 'high' in severities:
                result['severity'] = 'high'
                result['auto_action'] = 'mute'
            elif 'medium' in severities:
                result['severity'] = 'medium'
                result['auto_action'] = 'warn'
            else:
                result['severity'] = 'low'
        
        return result
    
    async def moderate_image(self, image_data: bytes) -> Dict[str, Any]:
        """Модерация изображения"""
        result = {
            'is_safe': True,
            'violations': [],
            'severity': 'low',
            'auto_action': None
        }
        
        if not self.image_moderation_enabled:
            return result
        
        try:
            # Открываем изображение
            image = Image.open(io.BytesIO(image_data))
            
            # Проверяем размеры (во избежание DoS)
            if image.width > 5000 or image.height > 5000:
                result['is_safe'] = False
                result['violations'].append({
                    'type': 'too_large',
                    'severity': 'medium'
                })
            
            # В реальном приложении здесь будет интеграция с сервисом модерации изображений
            # например, AWS Rekognition, Google Vision API и т.д.
            
        except Exception as e:
            result['is_safe'] = False
            result['violations'].append({
                'type': 'invalid_format',
                'error': str(e),
                'severity': 'high'
            })
        
        return result

class TranslationService:
    """Сервис перевода"""
    
    def __init__(self):
        self.supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh', 'ja', 'ko']
        self.translation_cache = {}
        self.cache_ttl = 3600  # 1 hour
    
    async def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """Перевод текста"""
        cache_key = f"{source_lang}:{target_lang}:{text[:50]}"
        
        # Проверяем кэш
        if cache_key in self.translation_cache:
            cached_result, timestamp = self.translation_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_result
        
        # В реальном приложении здесь будет вызов API перевода
        # например, Google Translate API, DeepL API и т.д.
        # Пока возвращаем оригинальный текст
        translated_text = text  # Заглушка
        
        # Сохраняем в кэш
        self.translation_cache[cache_key] = (translated_text, time.time())
        
        return translated_text
    
    def detect_language(self, text: str) -> str:
        """Определение языка текста"""
        # В реальном приложении использование библиотеки langdetect
        # или интеграции с API определения языка
        return 'en'  # Заглушка

class AIService:
    """Сервис искусственного интеллекта"""
    
    def __init__(self):
        self.ai_models = {}
        self.nlp_pipeline = None
        self.sentiment_analyzer = None
        self.summarizer = None
        self.chat_completions = None
    
    async def initialize_models(self):
        """Инициализация AI моделей"""
        try:
            # Инициализация NLP пайплайна
            self.nlp_pipeline = pipeline(
                "text-classification",
                model="distilbert-base-uncased-finetuned-sst-2-english"
            )
            
            # Инициализация анализатора тональности
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest"
            )
            
            # Инициализация суммаризатора
            self.summarizer = pipeline(
                "summarization",
                model="facebook/bart-large-cnn"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize AI models: {e}")
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Анализ тональности текста"""
        if not self.sentiment_analyzer:
            await self.initialize_models()
        
        try:
            result = self.sentiment_analyzer(text[:512])  # Ограничение длины
            return {
                'sentiment': result[0]['label'],
                'confidence': result[0]['score'],
                'text_preview': text[:100] + "..." if len(text) > 100 else text
            }
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {
                'sentiment': 'NEUTRAL',
                'confidence': 0.5,
                'error': str(e)
            }
    
    async def generate_smart_reply(self, message: str, context: List[str] = None) -> str:
        """Генерация умного ответа"""
        # В реальном приложении использование GPT или аналогичной модели
        # Пока возвращаем заглушку
        return "Thanks for your message!"
    
    async def summarize_text(self, text: str, max_length: int = 130) -> str:
        """Создание краткого содержания текста"""
        if not self.summarizer:
            await self.initialize_models()
        
        try:
            # Ограничиваем длину для модели
            if len(text) > 1024:
                text = text[:1024]
            
            result = self.summarizer(text, max_length=max_length, min_length=30, do_sample=False)
            return result[0]['summary_text']
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return text[:100] + "..." if len(text) > 100 else text

class SpamDetectionService:
    """Сервис обнаружения спама"""
    
    def __init__(self):
        self.spam_keywords = set()
        self.spam_urls = set()
        self.spam_senders = set()
        self.spam_model = None  # ML модель для обнаружения спама
        self.tfidf_vectorizer = TfidfVectorizer(max_features=10000, stop_words='english')
    
    def train_spam_model(self, spam_samples: List[str], ham_samples: List[str]):
        """Обучение модели обнаружения спама"""
        # Подготовка данных
        all_texts = spam_samples + ham_samples
        labels = [1] * len(spam_samples) + [0] * len(ham_samples)  # 1 - спам, 0 - не спам
        
        # Векторизация
        X = self.tfidf_vectorizer.fit_transform(all_texts)
        
        # Обучение модели (в реальном приложении использовать sklearn)
        from sklearn.linear_model import LogisticRegression
        self.spam_model = LogisticRegression()
        self.spam_model.fit(X, labels)
    
    async def is_spam(self, message: str, sender_id: int = None) -> bool:
        """Проверка сообщения на спам"""
        # Проверка ключевых слов
        message_lower = message.lower()
        for keyword in self.spam_keywords:
            if keyword in message_lower:
                return True
        
        # Проверка URL
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message)
        for url in urls:
            if url in self.spam_urls:
                return True
        
        # Проверка отправителя
        if sender_id and sender_id in self.spam_senders:
            return True
        
        # ML проверка
        if self.spam_model:
            vectorized = self.tfidf_vectorizer.transform([message])
            prediction = self.spam_model.predict(vectorized)[0]
            return bool(prediction)
        
        return False
    
    def add_spam_keyword(self, keyword: str):
        """Добавление ключевого слова спама"""
        self.spam_keywords.add(keyword.lower())
    
    def add_spam_url(self, url: str):
        """Добавление URL спама"""
        self.spam_urls.add(url)
    
    def add_spam_sender(self, sender_id: int):
        """Добавление отправителя спама"""
        self.spam_senders.add(sender_id)

class BackupService:
    """Сервис резервного копирования"""
    
    def __init__(self, s3_bucket: str = None, db_pool = None):
        self.s3_bucket = s3_bucket
        self.db_pool = db_pool
        self.backup_schedule = {}  # chat_id -> schedule
        self.s3_client = None
    
    async def initialize_s3(self, aws_access_key: str, aws_secret_key: str, region: str = 'us-east-1'):
        """Инициализация S3 клиента"""
        if self.s3_bucket:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=region
            )
    
    async def backup_chat_history(self, chat_id: str, days_back: int = 30) -> str:
        """Резервное копирование истории чата"""
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        async with self.db_pool.acquire() as conn:
            messages = await conn.fetch(
                """
                SELECT id, sender_id, content, message_type, timestamp, edited, edited_at
                FROM messages
                WHERE chat_id = $1 AND timestamp >= $2
                ORDER BY timestamp ASC
                """,
                chat_id, start_date
            )
        
        # Создаем резервную копию
        backup_data = {
            'chat_id': chat_id,
            'backup_date': datetime.utcnow().isoformat(),
            'messages': [
                {
                    'id': msg['id'],
                    'sender_id': msg['sender_id'],
                    'content': msg['content'],
                    'message_type': msg['message_type'],
                    'timestamp': msg['timestamp'].isoformat(),
                    'edited': msg['edited'],
                    'edited_at': msg['edited_at'].isoformat() if msg['edited_at'] else None
                }
                for msg in messages
            ]
        }
        
        # Сохраняем в S3 если настроено
        if self.s3_client and self.s3_bucket:
            backup_key = f"backups/chats/{chat_id}/{datetime.utcnow().strftime('%Y/%m/%d')}_backup.json"
            try:
                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=backup_key,
                    Body=json.dumps(backup_data, indent=2),
                    ContentType='application/json'
                )
                return f"s3://{self.s3_bucket}/{backup_key}"
            except ClientError as e:
                logger.error(f"S3 backup error: {e}")
        
        # Сохраняем локально как fallback
        backup_dir = f"backups/chats/{chat_id}/"
        import os
        os.makedirs(backup_dir, exist_ok=True)
        
        backup_file = f"{backup_dir}{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_backup.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        return backup_file
    
    async def restore_chat_history(self, backup_source: str, chat_id: str):
        """Восстановление истории чата из резервной копии"""
        # В реальном приложении реализация восстановления
        import logging
        logging.info(f"Restoring chat history for {chat_id} from {backup_source}")
        # В реальном приложении: реализация восстановления из резервной копии
        return True

class MonitoringService:
    """Сервис мониторинга"""
    
    def __init__(self, prometheus_client = None):
        self.prometheus = prometheus_client
        self.metrics = {}
        self.alerts = []
        self.health_checks = {}
    
    def add_metric(self, name: str, metric_type: str, description: str):
        """Добавление метрики"""
        if self.prometheus:
            if metric_type == 'counter':
                self.metrics[name] = self.prometheus.Counter(name, description)
            elif metric_type == 'gauge':
                self.metrics[name] = self.prometheus.Gauge(name, description)
            elif metric_type == 'histogram':
                self.metrics[name] = self.prometheus.Histogram(name, description)
    
    async def record_message_processed(self):
        """Запись обработки сообщения"""
        if 'messages_processed' in self.metrics:
            self.metrics['messages_processed'].inc()
    
    async def record_user_connected(self):
        """Запись подключения пользователя"""
        if 'active_users' in self.metrics:
            self.metrics['active_users'].inc()
    
    async def record_user_disconnected(self):
        """Запись отключения пользователя"""
        if 'active_users' in self.metrics:
            self.metrics['active_users'].dec()
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья сервиса"""
        checks = {}
        
        # Проверка базы данных
        try:
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks['database'] = {'status': 'healthy', 'latency': 0}
        except Exception as e:
            checks['database'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Проверка Redis
        try:
            await self.redis.ping()
            checks['redis'] = {'status': 'healthy', 'latency': 0}
        except Exception as e:
            checks['redis'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Проверка других сервисов...
        
        overall_status = 'healthy' if all(check['status'] == 'healthy' for check in checks.values()) else 'unhealthy'
        
        return {
            'status': overall_status,
            'checks': checks,
            'timestamp': datetime.utcnow().isoformat()
        }

# Глобальные экземпляры сервисов
notification_service = NotificationService(None, None)  # Будет инициализирован в основном приложении
analytics_service = AnalyticsService(None, None)
content_moderation_service = ContentModerationService()
translation_service = TranslationService()
ai_service = AIService()
spam_detection_service = SpamDetectionService()
backup_service = BackupService()
monitoring_service = MonitoringService(None)