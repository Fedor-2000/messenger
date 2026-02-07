# External Service Integration System
# File: services/integration_service/external_integrations.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import aiohttp
from urllib.parse import urlencode

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class IntegrationType(Enum):
    CALENDAR = "calendar"
    CRM = "crm"
    EMAIL = "email"
    STORAGE = "storage"
    PRODUCTIVITY = "productivity"
    SOCIAL = "social"
    DEVELOPER = "developer"
    PAYMENT = "payment"
    CUSTOM = "custom"

class IntegrationStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    SUSPENDED = "suspended"

class IntegrationEvent(Enum):
    AUTHORIZED = "authorized"
    DATA_SYNCED = "data_synced"
    ERROR_OCCURRED = "error_occurred"
    RATE_LIMITED = "rate_limited"
    DISCONNECTED = "disconnected"

class ExternalIntegration(BaseModel):
    id: str
    user_id: int
    integration_type: IntegrationType
    name: str
    description: str
    api_endpoint: str
    auth_method: str  # 'oauth', 'api_key', 'basic', 'custom'
    credentials: Dict[str, str]  # Зашифрованные учетные данные
    scopes: List[str]  # Разрешения
    status: IntegrationStatus
    webhook_url: Optional[str] = None
    settings: Optional[Dict] = None
    last_sync: Optional[datetime] = None
    next_sync: Optional[datetime] = None
    sync_interval: Optional[int] = None  # В секундах
    created_at: datetime = None
    updated_at: datetime = None
    enabled: bool = True

class IntegrationEventLog(BaseModel):
    id: str
    integration_id: str
    event_type: IntegrationEvent
    details: Dict[str, Any]
    timestamp: datetime = None

class IntegrationData(BaseModel):
    integration_id: str
    data_type: str  # 'calendar_event', 'contact', 'file', 'task', etc.
    external_id: str  # ID в внешней системе
    local_id: Optional[str] = None  # ID в нашей системе
    data: Dict[str, Any]
    synced_at: datetime = None
    last_modified: datetime = None

class ExternalIntegrationService:
    def __init__(self):
        self.integration_handlers = {
            IntegrationType.CALENDAR: CalendarIntegrationHandler(),
            IntegrationType.CRM: CrmIntegrationHandler(),
            IntegrationType.EMAIL: EmailIntegrationHandler(),
            IntegrationType.STORAGE: StorageIntegrationHandler(),
            IntegrationType.PRODUCTIVITY: ProductivityIntegrationHandler(),
            IntegrationType.SOCIAL: SocialIntegrationHandler(),
            IntegrationType.DEVELOPER: DeveloperIntegrationHandler(),
            IntegrationType.PAYMENT: PaymentIntegrationHandler(),
            IntegrationType.CUSTOM: CustomIntegrationHandler()
        }

    async def connect_integration(self, user_id: int, integration_type: IntegrationType,
                                 name: str, api_endpoint: str, auth_method: str,
                                 credentials: Dict[str, str], scopes: List[str],
                                 webhook_url: Optional[str] = None,
                                 settings: Optional[Dict] = None) -> Optional[str]:
        """Подключение к внешнему сервису"""
        integration_id = str(uuid.uuid4())

        integration = ExternalIntegration(
            id=integration_id,
            user_id=user_id,
            integration_type=integration_type,
            name=name,
            description=f"Integration with {name}",
            api_endpoint=api_endpoint,
            auth_method=auth_method,
            credentials=credentials,
            scopes=scopes,
            status=IntegrationStatus.CONNECTING,
            webhook_url=webhook_url,
            settings=settings or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            enabled=True
        )

        # Проверяем подключение
        handler = self.integration_handlers.get(integration_type)
        if not handler:
            return None

        try:
            is_connected = await handler.test_connection(integration)
            if is_connected:
                integration.status = IntegrationStatus.CONNECTED
            else:
                integration.status = IntegrationStatus.ERROR
        except Exception as e:
            logger.error(f"Error connecting to integration {integration_type}: {e}")
            integration.status = IntegrationStatus.ERROR

        # Сохраняем интеграцию в базу данных
        await self._save_integration(integration)

        # Добавляем в кэш
        await self._cache_integration(integration)

        # Логируем событие
        await self._log_integration_event(integration.id, IntegrationEvent.AUTHORIZED, {
            "api_endpoint": api_endpoint,
            "auth_method": auth_method
        })

        # Если подключение успешно, запускаем синхронизацию
        if integration.status == IntegrationStatus.CONNECTED:
            await self._schedule_initial_sync(integration)

        return integration_id if integration.status == IntegrationStatus.CONNECTED else None

    async def disconnect_integration(self, integration_id: str, user_id: int) -> bool:
        """Отключение от внешнего сервиса"""
        integration = await self.get_integration(integration_id)
        if not integration:
            return False

        # Проверяем права
        if integration.user_id != user_id:
            return False

        # Вызываем специфичный метод отключения для типа интеграции
        handler = self.integration_handlers.get(integration.integration_type)
        if handler:
            await handler.disconnect(integration)

        # Обновляем статус
        integration.status = IntegrationStatus.DISCONNECTED
        integration.enabled = False
        integration.updated_at = datetime.utcnow()

        # Сохраняем изменения
        await self._update_integration(integration)

        # Удаляем из кэша
        await self._uncache_integration(integration_id)

        # Логируем событие
        await self._log_integration_event(integration_id, IntegrationEvent.DISCONNECTED, {
            "reason": "user_requested"
        })

        return True

    async def get_integration(self, integration_id: str) -> Optional[ExternalIntegration]:
        """Получение интеграции по ID"""
        # Сначала проверяем кэш
        cached_integration = await self._get_cached_integration(integration_id)
        if cached_integration:
            return cached_integration

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, integration_type, name, description, api_endpoint,
                       auth_method, credentials, scopes, status, webhook_url, settings,
                       last_sync, next_sync, sync_interval, created_at, updated_at, enabled
                FROM external_integrations WHERE id = $1
                """,
                integration_id
            )

        if not row:
            return None

        integration = ExternalIntegration(
            id=row['id'],
            user_id=row['user_id'],
            integration_type=IntegrationType(row['integration_type']),
            name=row['name'],
            description=row['description'],
            api_endpoint=row['api_endpoint'],
            auth_method=row['auth_method'],
            credentials=row['credentials'],
            scopes=row['scopes'],
            status=IntegrationStatus(row['status']),
            webhook_url=row['webhook_url'],
            settings=row['settings'],
            last_sync=row['last_sync'],
            next_sync=row['next_sync'],
            sync_interval=row['sync_interval'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            enabled=row['enabled']
        )

        # Кэшируем интеграцию
        await self._cache_integration(integration)

        return integration

    async def get_user_integrations(self, user_id: int, 
                                  integration_type: Optional[IntegrationType] = None,
                                  status: Optional[IntegrationStatus] = None) -> List[ExternalIntegration]:
        """Получение интеграций пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if integration_type:
            conditions.append(f"integration_type = ${param_idx}")
            params.append(integration_type.value)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, user_id, integration_type, name, description, api_endpoint,
                   auth_method, credentials, scopes, status, webhook_url, settings,
                   last_sync, next_sync, sync_interval, created_at, updated_at, enabled
            FROM external_integrations
            WHERE {where_clause}
            ORDER BY created_at DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        integrations = []
        for row in rows:
            integration = ExternalIntegration(
                id=row['id'],
                user_id=row['user_id'],
                integration_type=IntegrationType(row['integration_type']),
                name=row['name'],
                description=row['description'],
                api_endpoint=row['api_endpoint'],
                auth_method=row['auth_method'],
                credentials=row['credentials'],
                scopes=row['scopes'],
                status=IntegrationStatus(row['status']),
                webhook_url=row['webhook_url'],
                settings=row['settings'],
                last_sync=row['last_sync'],
                next_sync=row['next_sync'],
                sync_interval=row['sync_interval'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                enabled=row['enabled']
            )
            integrations.append(integration)

        return integrations

    async def sync_integration_data(self, integration_id: str, user_id: int,
                                  data_types: Optional[List[str]] = None) -> bool:
        """Синхронизация данных с внешним сервисом"""
        integration = await self.get_integration(integration_id)
        if not integration:
            return False

        # Проверяем права
        if integration.user_id != user_id:
            return False

        # Проверяем статус
        if integration.status != IntegrationStatus.CONNECTED or not integration.enabled:
            return False

        handler = self.integration_handlers.get(integration.integration_type)
        if not handler:
            return False

        try:
            # Выполняем синхронизацию
            sync_result = await handler.sync_data(integration, data_types)

            # Обновляем время последней синхронизации
            integration.last_sync = datetime.utcnow()
            if integration.sync_interval:
                integration.next_sync = integration.last_sync + timedelta(seconds=integration.sync_interval)
            integration.updated_at = datetime.utcnow()

            # Сохраняем изменения
            await self._update_integration(integration)

            # Логируем событие
            await self._log_integration_event(integration_id, IntegrationEvent.DATA_SYNCED, {
                "data_types_synced": data_types or ["all"],
                "records_synced": sync_result.get("records_count", 0),
                "sync_duration": sync_result.get("duration", 0)
            })

            return True
        except Exception as e:
            logger.error(f"Error syncing integration {integration_id}: {e}")
            
            # Логируем ошибку
            await self._log_integration_event(integration_id, IntegrationEvent.ERROR_OCCURRED, {
                "error": str(e),
                "error_type": type(e).__name__
            })

            # При частых ошибках можем временно отключить интеграцию
            if await self._should_suspend_integration(integration_id):
                integration.status = IntegrationStatus.SUSPENDED
                await self._update_integration(integration)

            return False

    async def _save_integration(self, integration: ExternalIntegration):
        """Сохранение интеграции в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO external_integrations (
                    id, user_id, integration_type, name, description, api_endpoint,
                    auth_method, credentials, scopes, status, webhook_url, settings,
                    last_sync, next_sync, sync_interval, created_at, updated_at, enabled
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                """,
                integration.id, integration.user_id, integration.integration_type.value,
                integration.name, integration.description, integration.api_endpoint,
                integration.auth_method, json.dumps(integration.credentials),
                integration.scopes, integration.status.value, integration.webhook_url,
                json.dumps(integration.settings) if integration.settings else None,
                integration.last_sync, integration.next_sync, integration.sync_interval,
                integration.created_at, integration.updated_at, integration.enabled
            )

    async def _update_integration(self, integration: ExternalIntegration):
        """Обновление интеграции в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE external_integrations SET
                    status = $2, last_sync = $3, next_sync = $4, updated_at = $5,
                    enabled = $6
                WHERE id = $1
                """,
                integration.id, integration.status.value, integration.last_sync,
                integration.next_sync, integration.updated_at, integration.enabled
            )

    async def _cache_integration(self, integration: ExternalIntegration):
        """Кэширование интеграции"""
        await redis_client.setex(f"integration:{integration.id}", 300, 
                                integration.model_dump_json())

    async def _get_cached_integration(self, integration_id: str) -> Optional[ExternalIntegration]:
        """Получение интеграции из кэша"""
        cached = await redis_client.get(f"integration:{integration_id}")
        if cached:
            return ExternalIntegration(**json.loads(cached))
        return None

    async def _uncache_integration(self, integration_id: str):
        """Удаление интеграции из кэша"""
        await redis_client.delete(f"integration:{integration_id}")

    async def _log_integration_event(self, integration_id: str, event_type: IntegrationEvent,
                                   details: Dict[str, Any]):
        """Логирование события интеграции"""
        event_id = str(uuid.uuid4())
        event = IntegrationEventLog(
            id=event_id,
            integration_id=integration_id,
            event_type=event_type,
            details=details,
            timestamp=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO integration_events (id, integration_id, event_type, details, timestamp)
                VALUES ($1, $2, $3, $4, $5)
                """,
                event.id, event.integration_id, event.event_type.value,
                json.dumps(event.details), event.timestamp
            )

    async def _schedule_initial_sync(self, integration: ExternalIntegration):
        """Планирование начальной синхронизации"""
        if not integration.sync_interval:
            return

        next_sync_time = datetime.utcnow() + timedelta(seconds=integration.sync_interval)
        integration.next_sync = next_sync_time

        # Сохраняем обновленное время следующей синхронизации
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE external_integrations SET next_sync = $2 WHERE id = $1",
                integration.id, next_sync_time
            )

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "integration_sync_queue",
            {integration.id: next_sync_time.timestamp()}
        )

    async def _should_suspend_integration(self, integration_id: str) -> bool:
        """Проверка, нужно ли временно отключить интеграцию из-за ошибок"""
        # Проверяем последние события интеграции
        async with db_pool.acquire() as conn:
            recent_errors = await conn.fetch(
                """
                SELECT COUNT(*) as error_count
                FROM integration_events
                WHERE integration_id = $1 
                    AND event_type = 'error_occurred'
                    AND timestamp > $2
                """,
                integration_id, datetime.utcnow() - timedelta(hours=1)
            )

        # Если больше 5 ошибок за последний час, приостанавливаем
        return recent_errors[0]['error_count'] > 5

    async def handle_webhook(self, integration_id: str, payload: Dict[str, Any]) -> bool:
        """Обработка вебхука от внешнего сервиса"""
        integration = await self.get_integration(integration_id)
        if not integration:
            return False

        handler = self.integration_handlers.get(integration.integration_type)
        if not handler:
            return False

        try:
            # Обрабатываем пейлоад в зависимости от типа интеграции
            processed_data = await handler.process_webhook_payload(integration, payload)

            # Синхронизируем данные
            await self.sync_integration_data(integration_id, integration.user_id)

            # Логируем событие
            await self._log_integration_event(integration_id, IntegrationEvent.DATA_SYNCED, {
                "webhook_processed": True,
                "payload_keys": list(payload.keys())
            })

            return True
        except Exception as e:
            logger.error(f"Error processing webhook for integration {integration_id}: {e}")
            
            await self._log_integration_event(integration_id, IntegrationEvent.ERROR_OCCURRED, {
                "error": str(e),
                "webhook_payload": payload
            })

            return False

class BaseIntegrationHandler:
    """Базовый класс для обработчиков интеграций"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к сервису"""
        # Base implementation - try to make a simple API request
        try:
            response = await self._make_api_request(integration, 'GET', 'test')
            return response is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    async def disconnect(self, integration: ExternalIntegration):
        """Отключение от сервиса"""
        # Базовая реализация - логируем отключение
        import logging
        logging.info(f"Disconnecting from integration {integration.id}")
        return True

    async def sync_data(self, integration: ExternalIntegration,
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных"""
        start_time = datetime.utcnow()

        data_types = data_types or []
        records_count = 0

        # В реальной системе здесь будет синхронизация данных из внешнего сервиса
        # Для упрощения возвращаем пустой результат
        logger.info(f"Syncing data for {integration.integration_type}")

        duration = (datetime.utcnow() - start_time).total_seconds()

        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types,
            "message": "Data sync completed"
        }

    async def process_webhook_payload(self, integration: ExternalIntegration,
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука"""
        logger.info(f"Processing webhook payload for {integration.integration_type}")

        # В реальной системе здесь будет обработка пейлоада вебхука
        # в зависимости от типа интеграции и содержания пейлоада
        processed_data = {
            "processed": True,
            "integration_id": integration.id,
            "payload_type": payload.get('type', 'unknown'),
            "processed_at": datetime.utcnow().isoformat()
        }

        return processed_data

    async def _make_api_request(self, integration: ExternalIntegration, method: str, 
                              endpoint: str, data: Optional[Dict] = None,
                              params: Optional[Dict] = None) -> Optional[Dict]:
        """Выполнение API запроса к внешнему сервису"""
        headers = await self._get_auth_headers(integration)
        
        url = f"{integration.api_endpoint.rstrip('/')}/{endpoint.lstrip('/')}"
        
        async with aiohttp.ClientSession() as session:
            try:
                if method.upper() == 'GET':
                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"API request failed: {response.status}, {await response.text()}")
                            return None
                elif method.upper() == 'POST':
                    async with session.post(url, headers=headers, json=data, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"API request failed: {response.status}, {await response.text()}")
                            return None
                elif method.upper() == 'PUT':
                    async with session.put(url, headers=headers, json=data, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"API request failed: {response.status}, {await response.text()}")
                            return None
                elif method.upper() == 'DELETE':
                    async with session.delete(url, headers=headers, params=params) as response:
                        if response.status in [200, 204]:
                            return {} if response.status == 204 else await response.json()
                        else:
                            logger.error(f"API request failed: {response.status}, {await response.text()}")
                            return None
            except Exception as e:
                logger.error(f"Error making API request: {e}")
                return None

    async def _get_auth_headers(self, integration: ExternalIntegration) -> Dict[str, str]:
        """Получение заголовков аутентификации"""
        headers = {"Content-Type": "application/json"}
        
        if integration.auth_method == 'api_key':
            headers["Authorization"] = f"Bearer {integration.credentials.get('api_key', '')}"
        elif integration.auth_method == 'oauth':
            headers["Authorization"] = f"Bearer {integration.credentials.get('access_token', '')}"
        elif integration.auth_method == 'basic':
            import base64
            credentials = f"{integration.credentials.get('username', '')}:{integration.credentials.get('password', '')}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_credentials}"
        
        return headers

class CalendarIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с календарем"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к календарю"""
        # Пытаемся получить список календарей
        response = await self._make_api_request(integration, 'GET', 'calendars')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация календарных событий"""
        start_time = datetime.utcnow()
        
        data_types = data_types or ['events']
        records_count = 0
        
        if 'events' in data_types:
            # Получаем события за последнюю неделю
            since = (datetime.utcnow() - timedelta(weeks=1)).isoformat()
            params = {'timeMin': since}
            
            events_response = await self._make_api_request(integration, 'GET', 'events', params=params)
            if events_response:
                for event_data in events_response.get('items', []):
                    # Сохраняем событие
                    await self._save_calendar_event(integration, event_data)
                    records_count += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types
        }

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука календаря"""
        # Обрабатываем изменения событий
        changes = payload.get('changes', [])
        
        for change in changes:
            event_id = change.get('eventId')
            change_type = change.get('type')  # 'create', 'update', 'delete'
            
            if change_type == 'delete':
                await self._delete_calendar_event(integration, event_id)
            else:
                event_data = await self._make_api_request(integration, 'GET', f'events/{event_id}')
                if event_data:
                    await self._save_calendar_event(integration, event_data)
        
        return {"processed_changes": len(changes)}

    async def _save_calendar_event(self, integration: ExternalIntegration, event_data: Dict[str, Any]):
        """Сохранение календарного события"""
        # Сохраняем в нашу базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO calendar_events (
                    external_id, integration_id, title, description, start_time, end_time,
                    timezone, creator_id, event_type, privacy, location, recurrence_pattern,
                    recurrence_end, reminder_minutes, created_at, updated_at, chat_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (external_id) DO UPDATE SET
                    title = $3, description = $4, start_time = $5, end_time = $6,
                    timezone = $7, event_type = $9, privacy = $10, location = $11,
                    recurrence_pattern = $12, recurrence_end = $13, reminder_minutes = $14,
                    updated_at = $16
                """,
                event_data.get('id'), integration.id, 
                event_data.get('summary', ''), event_data.get('description', ''),
                event_data.get('start', {}).get('dateTime'), 
                event_data.get('end', {}).get('dateTime'),
                event_data.get('timeZone', 'UTC'), integration.user_id,
                'external', 'private', event_data.get('location', ''),
                event_data.get('recurrence', [])[0] if event_data.get('recurrence') else None,
                event_data.get('recurrence', [{}])[0].get('end') if event_data.get('recurrence') else None,
                event_data.get('reminders', {}).get('useDefault', 15),
                datetime.utcnow(), datetime.utcnow(), None
            )

    async def _delete_calendar_event(self, integration: ExternalIntegration, event_id: str):
        """Удаление календарного события"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM calendar_events WHERE external_id = $1 AND integration_id = $2",
                event_id, integration.id
            )

class CrmIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с CRM"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к CRM"""
        # Пытаемся получить профиль пользователя
        response = await self._make_api_request(integration, 'GET', 'users/me')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных CRM"""
        start_time = datetime.utcnow()
        
        data_types = data_types or ['contacts', 'deals', 'activities']
        records_count = 0
        
        for data_type in data_types:
            if data_type == 'contacts':
                contacts_response = await self._make_api_request(integration, 'GET', 'contacts')
                if contacts_response:
                    for contact_data in contacts_response.get('data', []):
                        await self._save_contact(integration, contact_data)
                        records_count += 1
            elif data_type == 'deals':
                deals_response = await self._make_api_request(integration, 'GET', 'deals')
                if deals_response:
                    for deal_data in deals_response.get('data', []):
                        await self._save_deal(integration, deal_data)
                        records_count += 1
            elif data_type == 'activities':
                activities_response = await self._make_api_request(integration, 'GET', 'activities')
                if activities_response:
                    for activity_data in activities_response.get('data', []):
                        await self._save_activity(integration, activity_data)
                        records_count += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types
        }

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука CRM"""
        # Обрабатываем изменения в CRM
        event_type = payload.get('event')
        object_type = payload.get('object')
        object_data = payload.get('data', {})
        
        if object_type == 'contact':
            if event_type in ['created', 'updated']:
                await self._save_contact(integration, object_data)
            elif event_type == 'deleted':
                await self._delete_contact(integration, object_data.get('id'))
        elif object_type == 'deal':
            if event_type in ['created', 'updated']:
                await self._save_deal(integration, object_data)
            elif event_type == 'deleted':
                await self._delete_deal(integration, object_data.get('id'))
        
        return {"processed_object_type": object_type, "event_type": event_type}

    async def _save_contact(self, integration: ExternalIntegration, contact_data: Dict[str, Any]):
        """Сохранение контакта из CRM"""
        # Сохраняем контакт в нашу систему
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crm_contacts (
                    external_id, integration_id, user_id, first_name, last_name,
                    email, phone, company, job_title, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (external_id) DO UPDATE SET
                    first_name = $4, last_name = $5, email = $6, phone = $7,
                    company = $8, job_title = $9, updated_at = $11
                """,
                contact_data.get('id'), integration.id, integration.user_id,
                contact_data.get('first_name', ''), contact_data.get('last_name', ''),
                contact_data.get('email', ''), contact_data.get('phone', ''),
                contact_data.get('company', ''), contact_data.get('job_title', ''),
                datetime.utcnow(), datetime.utcnow()
            )

    async def _save_deal(self, integration: ExternalIntegration, deal_data: Dict[str, Any]):
        """Сохранение сделки из CRM"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crm_deals (
                    external_id, integration_id, user_id, title, value, currency,
                    stage, status, contact_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (external_id) DO UPDATE SET
                    title = $4, value = $5, currency = $6, stage = $7, status = $8,
                    contact_id = $9, updated_at = $11
                """,
                deal_data.get('id'), integration.id, integration.user_id,
                deal_data.get('title', ''), deal_data.get('value', 0),
                deal_data.get('currency', 'USD'), deal_data.get('stage', ''),
                deal_data.get('status', 'open'), deal_data.get('contact_id'),
                datetime.utcnow(), datetime.utcnow()
            )

    async def _save_activity(self, integration: ExternalIntegration, activity_data: Dict[str, Any]):
        """Сохранение активности из CRM"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crm_activities (
                    external_id, integration_id, user_id, subject, type, status,
                    due_date, completed_date, contact_id, deal_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (external_id) DO UPDATE SET
                    subject = $4, type = $5, status = $6, due_date = $7,
                    completed_date = $8, contact_id = $9, deal_id = $10, updated_at = $12
                """,
                activity_data.get('id'), integration.id, integration.user_id,
                activity_data.get('subject', ''), activity_data.get('type', ''),
                activity_data.get('status', 'pending'), 
                activity_data.get('due_date'), activity_data.get('completed_date'),
                activity_data.get('contact_id'), activity_data.get('deal_id'),
                datetime.utcnow(), datetime.utcnow()
            )

    async def _delete_contact(self, integration: ExternalIntegration, contact_id: str):
        """Удаление контакта"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM crm_contacts WHERE external_id = $1 AND integration_id = $2",
                contact_id, integration.id
            )

    async def _delete_deal(self, integration: ExternalIntegration, deal_id: str):
        """Удаление сделки"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM crm_deals WHERE external_id = $1 AND integration_id = $2",
                deal_id, integration.id
            )

class EmailIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с email"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к email"""
        # Пытаемся получить список папок
        response = await self._make_api_request(integration, 'GET', 'folders')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация email данных"""
        start_time = datetime.utcnow()
        
        data_types = data_types or ['emails']
        records_count = 0
        
        if 'emails' in data_types:
            # Получаем последние письма
            params = {'limit': 50, 'sort': 'date', 'direction': 'desc'}
            emails_response = await self._make_api_request(integration, 'GET', 'messages', params=params)
            
            if emails_response:
                for email_data in emails_response.get('messages', []):
                    await self._save_email(integration, email_data)
                    records_count += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types
        }

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука email"""
        # Обрабатываем новые письма
        if payload.get('event') == 'new_message':
            email_id = payload.get('message_id')
            email_data = await self._make_api_request(integration, 'GET', f'messages/{email_id}')
            if email_data:
                await self._save_email(integration, email_data)
        
        return {"processed_emails": 1 if payload.get('event') == 'new_message' else 0}

    async def _save_email(self, integration: ExternalIntegration, email_data: Dict[str, Any]):
        """Сохранение email"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO email_messages (
                    external_id, integration_id, user_id, subject, sender, recipients,
                    body, body_html, received_at, is_read, folder, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (external_id) DO UPDATE SET
                    subject = $4, sender = $5, recipients = $6, body = $7, body_html = $8,
                    received_at = $9, is_read = $10, folder = $11, updated_at = $13
                """,
                email_data.get('id'), integration.id, integration.user_id,
                email_data.get('subject', ''), email_data.get('sender', ''),
                json.dumps(email_data.get('recipients', [])), 
                email_data.get('body', ''), email_data.get('body_html', ''),
                email_data.get('received_at'), email_data.get('is_read', False),
                email_data.get('folder', 'inbox'), datetime.utcnow(), datetime.utcnow()
            )

class StorageIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с облачным хранилищем"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к облачному хранилищу"""
        # Пытаемся получить информацию о пользователе
        response = await self._make_api_request(integration, 'GET', 'account')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация файлов из облачного хранилища"""
        start_time = datetime.utcnow()
        
        data_types = data_types or ['files']
        records_count = 0
        
        if 'files' in data_types:
            # Получаем список файлов в корневой папке
            params = {'folder': 'root', 'limit': 100}
            files_response = await self._make_api_request(integration, 'GET', 'files', params=params)
            
            if files_response:
                for file_data in files_response.get('files', []):
                    await self._save_file(integration, file_data)
                    records_count += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types
        }

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука облачного хранилища"""
        # Обрабатываем изменения файлов
        event_type = payload.get('event_type')
        file_data = payload.get('file', {})
        
        if event_type in ['file_created', 'file_updated']:
            await self._save_file(integration, file_data)
        elif event_type == 'file_deleted':
            await self._delete_file(integration, file_data.get('id'))
        
        return {"processed_event": event_type}

    async def _save_file(self, integration: ExternalIntegration, file_data: Dict[str, Any]):
        """Сохранение файла из облачного хранилища"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO storage_files (
                    external_id, integration_id, user_id, name, path, size, mime_type,
                    created_at, modified_at, download_url, thumbnail_url, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (external_id) DO UPDATE SET
                    name = $4, path = $5, size = $6, mime_type = $7, modified_at = $9,
                    download_url = $10, thumbnail_url = $11, updated_at = $13
                """,
                file_data.get('id'), integration.id, integration.user_id,
                file_data.get('name', ''), file_data.get('path', ''),
                file_data.get('size', 0), file_data.get('mime_type', ''),
                file_data.get('created_at'), file_data.get('modified_at'),
                file_data.get('download_url'), file_data.get('thumbnail_url'),
                datetime.utcnow(), datetime.utcnow()
            )

    async def _delete_file(self, integration: ExternalIntegration, file_id: str):
        """Удаление файла"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM storage_files WHERE external_id = $1 AND integration_id = $2",
                file_id, integration.id
            )

class ProductivityIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с продуктивными приложениями"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к продуктивному приложению"""
        # Пытаемся получить профиль пользователя
        response = await self._make_api_request(integration, 'GET', 'users/me')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных продуктивности"""
        start_time = datetime.utcnow()
        
        data_types = data_types or ['tasks', 'projects', 'time_entries']
        records_count = 0
        
        for data_type in data_types:
            if data_type == 'tasks':
                tasks_response = await self._make_api_request(integration, 'GET', 'tasks')
                if tasks_response:
                    for task_data in tasks_response.get('data', []):
                        await self._save_productivity_task(integration, task_data)
                        records_count += 1
            elif data_type == 'projects':
                projects_response = await self._make_api_request(integration, 'GET', 'projects')
                if projects_response:
                    for project_data in projects_response.get('data', []):
                        await self._save_project(integration, project_data)
                        records_count += 1
            elif data_type == 'time_entries':
                entries_response = await self._make_api_request(integration, 'GET', 'time_entries')
                if entries_response:
                    for entry_data in entries_response.get('data', []):
                        await self._save_time_entry(integration, entry_data)
                        records_count += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "records_count": records_count,
            "duration": duration,
            "data_types_synced": data_types
        }

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука продуктивности"""
        # Обрабатываем изменения в продуктивном приложении
        event_type = payload.get('event')
        object_type = payload.get('object')
        object_data = payload.get('data', {})
        
        if object_type == 'task':
            if event_type in ['created', 'updated']:
                await self._save_productivity_task(integration, object_data)
            elif event_type == 'deleted':
                await self._delete_productivity_task(integration, object_data.get('id'))
        
        return {"processed_object_type": object_type, "event_type": event_type}

    async def _save_productivity_task(self, integration: ExternalIntegration, task_data: Dict[str, Any]):
        """Сохранение задачи из продуктивного приложения"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO productivity_tasks (
                    external_id, integration_id, user_id, title, description, status,
                    priority, due_date, completed_at, project_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (external_id) DO UPDATE SET
                    title = $4, description = $5, status = $6, priority = $7,
                    due_date = $8, completed_at = $9, project_id = $10, updated_at = $12
                """,
                task_data.get('id'), integration.id, integration.user_id,
                task_data.get('title', ''), task_data.get('description', ''),
                task_data.get('status', 'todo'), task_data.get('priority', 'medium'),
                task_data.get('due_date'), task_data.get('completed_at'),
                task_data.get('project_id'), datetime.utcnow(), datetime.utcnow()
            )

    async def _save_project(self, integration: ExternalIntegration, project_data: Dict[str, Any]):
        """Сохранение проекта"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO productivity_projects (
                    external_id, integration_id, user_id, name, description, status,
                    start_date, end_date, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (external_id) DO UPDATE SET
                    name = $4, description = $5, status = $6, start_date = $7,
                    end_date = $8, updated_at = $10
                """,
                project_data.get('id'), integration.id, integration.user_id,
                project_data.get('name', ''), project_data.get('description', ''),
                project_data.get('status', 'active'), project_data.get('start_date'),
                project_data.get('end_date'), datetime.utcnow(), datetime.utcnow()
            )

    async def _save_time_entry(self, integration: ExternalIntegration, entry_data: Dict[str, Any]):
        """Сохранение записи времени"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO productivity_time_entries (
                    external_id, integration_id, user_id, task_id, project_id, description,
                    start_time, end_time, duration, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (external_id) DO UPDATE SET
                    task_id = $4, project_id = $5, description = $6, start_time = $7,
                    end_time = $8, duration = $9, updated_at = $11
                """,
                entry_data.get('id'), integration.id, integration.user_id,
                entry_data.get('task_id'), entry_data.get('project_id'),
                entry_data.get('description', ''), entry_data.get('start_time'),
                entry_data.get('end_time'), entry_data.get('duration'),
                datetime.utcnow(), datetime.utcnow()
            )

    async def _delete_productivity_task(self, integration: ExternalIntegration, task_id: str):
        """Удаление задачи"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM productivity_tasks WHERE external_id = $1 AND integration_id = $2",
                task_id, integration.id
            )

# Другие обработчики (SocialIntegrationHandler, DeveloperIntegrationHandler, 
# PaymentIntegrationHandler, CustomIntegrationHandler) будут реализованы аналогично

class SocialIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с социальными сетями"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к социальной сети"""
        # Пытаемся получить профиль пользователя
        response = await self._make_api_request(integration, 'GET', 'me')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных из социальной сети"""
        # Реализация будет зависеть от конкретной социальной сети
        return {"records_count": 0, "duration": 0, "data_types_synced": data_types or []}

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука социальной сети"""
        return {}

class DeveloperIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с разработческими инструментами"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к разработческому инструменту"""
        # Пытаемся получить список проектов
        response = await self._make_api_request(integration, 'GET', 'projects')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных из разработческого инструмента"""
        # Реализация будет зависеть от конкретного инструмента
        return {"records_count": 0, "duration": 0, "data_types_synced": data_types or []}

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука разработческого инструмента"""
        return {}

class PaymentIntegrationHandler(BaseIntegrationHandler):
    """Обработчик интеграции с платежными системами"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к платежной системе"""
        # Пытаемся получить баланс
        response = await self._make_api_request(integration, 'GET', 'balance')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных из платежной системы"""
        # Реализация будет зависеть от конкретной платежной системы
        return {"records_count": 0, "duration": 0, "data_types_synced": data_types or []}

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука платежной системы"""
        return {}

class CustomIntegrationHandler(BaseIntegrationHandler):
    """Обработчик пользовательских интеграций"""
    
    async def test_connection(self, integration: ExternalIntegration) -> bool:
        """Проверка подключения к пользовательской интеграции"""
        # Пытаемся выполнить тестовый запрос
        response = await self._make_api_request(integration, 'GET', 'test')
        return response is not None

    async def sync_data(self, integration: ExternalIntegration, 
                       data_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Синхронизация данных из пользовательской интеграции"""
        # Реализация будет зависеть от пользовательской конфигурации
        return {"records_count": 0, "duration": 0, "data_types_synced": data_types or []}

    async def process_webhook_payload(self, integration: ExternalIntegration, 
                                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вебхука пользовательской интеграции"""
        return {}

# Глобальный экземпляр для использования в приложении
external_integration_service = ExternalIntegrationService()