# gRPC Service Communication Layer
# File: services/grpc_service/grpc_communication.py

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import uuid

import grpc
from concurrent import futures
import proto.messenger_pb2 as pb2
import proto.messenger_pb2_grpc as pb2_grpc

logger = logging.getLogger(__name__)

class GRPCCommunicationService:
    def __init__(self):
        self.services = {}
        self.interceptors = []
        self.middleware = []
        self.grpc_port = 50051
        self.max_workers = 10
        self.server = None

    async def initialize_grpc_services(self):
        """Инициализация gRPC сервисов"""
        # Создаем сервер
        self.server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers),
            interceptors=self.interceptors
        )

        # Регистрируем сервисы
        self._register_auth_service()
        self._register_chat_service()
        self._register_file_service()
        self._register_notification_service()
        self._register_task_service()
        self._register_calendar_service()
        self._register_game_service()
        self._register_call_service()

        # Добавляем middleware
        self._add_grpc_middleware()

    def _register_auth_service(self):
        """Регистрация gRPC сервиса аутентификации"""
        # В реальной системе здесь будет регистрация AuthServicer
        # auth_servicer = AuthServicer()
        # pb2_grpc.add_AuthServicer_to_server(auth_servicer, self.server)
        import logging
        logging.info("Auth service registration called (stub implementation)")
        return True

    def _register_chat_service(self):
        """Регистрация gRPC сервиса чатов"""
        # В реальной системе здесь будет регистрация ChatServicer
        # chat_servicer = ChatServicer()
        # pb2_grpc.add_ChatServicer_to_server(chat_servicer, self.server)
        import logging
        logging.info("Chat service registration called (stub implementation)")
        return True

    def _register_file_service(self):
        """Регистрация gRPC сервиса файлов"""
        # В реальной системе здесь будет регистрация FileServicer
        # file_servicer = FileServicer()
        # pb2_grpc.add_FileServicer_to_server(file_servicer, self.server)
        import logging
        logging.info("File service registration called (stub implementation)")
        return True

    def _register_notification_service(self):
        """Регистрация gRPC сервиса уведомлений"""
        # В реальной системе здесь будет регистрация NotificationServicer
        # notification_servicer = NotificationServicer()
        # pb2_grpc.add_NotificationServicer_to_server(notification_servicer, self.server)
        import logging
        logging.info("Notification service registration called (stub implementation)")
        return True

    def _register_task_service(self):
        """Регистрация gRPC сервиса задач"""
        # В реальной системе здесь будет регистрация TaskServicer
        # task_servicer = TaskServicer()
        # pb2_grpc.add_TaskServicer_to_server(task_servicer, self.server)
        import logging
        logging.info("Task service registration called (stub implementation)")
        return True

    def _register_calendar_service(self):
        """Регистрация gRPC сервиса календаря"""
        # В реальной системе здесь будет регистрация CalendarServicer
        # calendar_servicer = CalendarServicer()
        # pb2_grpc.add_CalendarServicer_to_server(calendar_servicer, self.server)
        import logging
        logging.info("Calendar service registration called (stub implementation)")
        return True

    def _register_game_service(self):
        """Регистрация gRPC сервиса игр"""
        # В реальной системе здесь будет регистрация GameServicer
        # game_servicer = GameServicer()
        # pb2_grpc.add_GameServicer_to_server(game_servicer, self.server)
        import logging
        logging.info("Game service registration called (stub implementation)")
        return True

    def _register_call_service(self):
        """Регистрация gRPC сервиса звонков"""
        # В реальной системе здесь будет регистрация CallServicer
        # call_servicer = CallServicer()
        # pb2_grpc.add_CallServicer_to_server(call_servicer, self.server)
        import logging
        logging.info("Call service registration called (stub implementation)")
        return True

    def _add_grpc_middleware(self):
        """Добавление gRPC middleware"""
        # Добавляем middleware для логирования
        self.middleware.append(self._grpc_logging_middleware)
        
        # Добавляем middleware для аутентификации
        self.middleware.append(self._grpc_authentication_middleware)
        
        # Добавляем middleware для мониторинга
        self.middleware.append(self._grpc_monitoring_middleware)

    async def start_grpc_server(self):
        """Запуск gRPC сервера"""
        self.server.add_insecure_port(f'[::]:{self.grpc_port}')
        
        try:
            await self.server.start()
            logger.info(f"gRPC server started on port {self.grpc_port}")
            
            # Ожидаем завершения работы
            await self.server.wait_for_termination()
        except KeyboardInterrupt:
            logger.info("Shutting down gRPC server...")
            await self.server.stop(grace=5)
        except Exception as e:
            logger.error(f"Error starting gRPC server: {e}")

    async def _grpc_logging_middleware(self, continuation, handler_call_details, request):
        """Middleware для логирования gRPC вызовов"""
        start_time = datetime.utcnow()
        
        try:
            response = await continuation(handler_call_details, request)
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000  # в миллисекундах
            
            logger.info(f"gRPC call {handler_call_details.method} completed in {duration:.2f}ms")
            
            return response
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"gRPC call {handler_call_details.method} failed after {duration:.2f}ms: {e}")
            raise

    async def _grpc_authentication_middleware(self, continuation, handler_call_details, request):
        """Middleware для аутентификации gRPC вызовов"""
        # Проверяем метаданные вызова на наличие токена аутентификации
        metadata = dict(handler_call_details.invocation_metadata)
        
        auth_token = metadata.get('authorization', '').replace('Bearer ', '')
        if not auth_token:
            # Проверяем в заголовках
            auth_token = metadata.get('auth-token', '')
        
        if not auth_token:
            # Для внутрисервисных вызовов может быть специальный токен
            service_token = metadata.get('service-token', '')
            if not service_token:
                # Возвращаем ошибку аутентификации
                raise grpc.aio.AbortError(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
        
        # Проверяем токен (в реальной системе здесь будет проверка через auth сервис)
        # is_valid = await self._validate_grpc_token(auth_token)
        # if not is_valid:
        #     raise grpc.aio.AbortError(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        
        return await continuation(handler_call_details, request)

    async def _grpc_monitoring_middleware(self, continuation, handler_call_details, request):
        """Middleware для мониторинга gRPC вызовов"""
        start_time = datetime.utcnow()
        
        try:
            response = await continuation(handler_call_details, request)
            
            # Записываем метрику производительности
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000  # в миллисекундах
            
            # В реальной системе здесь будет отправка метрики в Prometheus
            # await self._record_grpc_metric(handler_call_details.method, duration, "success")
            
            return response
        except Exception as e:
            # Записываем метрику ошибки
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # В реальной системе здесь будет отправка метрики в Prometheus
            # await self._record_grpc_metric(handler_call_details.method, duration, "error")
            
            raise

    async def _validate_grpc_token(self, token: str) -> bool:
        """Проверка токена аутентификации gRPC"""
        # В реальной системе здесь будет вызов auth сервиса для проверки токена
        # Для упрощения возвращаем True
        return True

    async def _record_grpc_metric(self, method: str, duration: float, status: str):
        """Запись метрики gRPC вызова"""
        # В реальной системе здесь будет отправка в Prometheus
        import logging
        logging.info(f"gRPC metric recorded: method={method}, duration={duration}s, status={status}")
        return True

    async def create_grpc_client(self, service_name: str, target: str) -> Any:
        """Создание gRPC клиента для взаимодействия с сервисом"""
        # Реализуем полноценное создание gRPC клиента
        try:
            import grpc
            import proto.messenger_pb2_grpc as pb2_grpc

            # Создаем асинхронный канал
            channel = grpc.aio.insecure_channel(target)

            # В зависимости от имени сервиса создаем соответствующий stub
            if service_name == 'auth':
                stub = pb2_grpc.AuthStub(channel)
            elif service_name == 'chat':
                stub = pb2_grpc.ChatStub(channel)
            elif service_name == 'file':
                stub = pb2_grpc.FileStub(channel)
            elif service_name == 'notification':
                stub = pb2_grpc.NotificationStub(channel)
            elif service_name == 'task':
                stub = pb2_grpc.TaskStub(channel)
            elif service_name == 'calendar':
                stub = pb2_grpc.CalendarStub(channel)
            elif service_name == 'game':
                stub = pb2_grpc.GameStub(channel)
            elif service_name == 'call':
                stub = pb2_grpc.CallStub(channel)
            else:
                logger.warning(f"Unknown service name: {service_name}")
                await channel.close()
                return None

            # Сохраняем канал для последующего закрытия
            if not hasattr(self, '_channels'):
                self._channels = {}
            self._channels[f"{service_name}_{target}"] = channel

            logger.info(f"gRPC client created successfully for {service_name} at {target}")
            return stub

        except Exception as e:
            logger.error(f"Error creating gRPC client for {service_name} at {target}: {e}")
            return None

    async def call_auth_service(self, method: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Вызов метода сервиса аутентификации через gRPC"""
        try:
            # Получаем клиент для auth сервиса
            auth_stub = await self.create_grpc_client("auth", "auth-service:50051")
            
            # Выполняем вызов
            if method == "authenticate_user":
                request = pb2.AuthenticateUserRequest(
                    username=request_data.get("username", ""),
                    password=request_data.get("password", ""),
                    tfa_code=request_data.get("tfa_code", "")
                )
                response = await auth_stub.AuthenticateUser(request)
            elif method == "create_user":
                request = pb2.CreateUserRequest(
                    username=request_data.get("username", ""),
                    password=request_data.get("password", ""),
                    email=request_data.get("email", "")
                )
                response = await auth_stub.CreateUser(request)
            elif method == "refresh_token":
                request = pb2.RefreshTokenRequest(
                    refresh_token=request_data.get("refresh_token", "")
                )
                response = await auth_stub.RefreshToken(request)
            else:
                logger.error(f"Unknown auth method: {method}")
                return None
            
            return {
                "success": True,
                "data": response
            }
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC call to auth service failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error calling auth service: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def call_chat_service(self, method: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Вызов метода сервиса чатов через gRPC"""
        try:
            # Получаем клиент для chat сервиса
            chat_stub = await self.create_grpc_client("chat", "chat-service:50052")
            
            # Выполняем вызов
            if method == "send_message":
                request = pb2.SendMessageRequest(
                    chat_id=request_data.get("chat_id", ""),
                    sender_id=request_data.get("sender_id", 0),
                    content=request_data.get("content", ""),
                    message_type=request_data.get("message_type", "text")
                )
                response = await chat_stub.SendMessage(request)
            elif method == "create_chat":
                request = pb2.CreateChatRequest(
                    name=request_data.get("name", ""),
                    type=request_data.get("type", "private"),
                    creator_id=request_data.get("creator_id", 0),
                    participants=request_data.get("participants", [])
                )
                response = await chat_stub.CreateChat(request)
            elif method == "get_chat_history":
                request = pb2.GetChatHistoryRequest(
                    chat_id=request_data.get("chat_id", ""),
                    limit=request_data.get("limit", 50),
                    offset=request_data.get("offset", 0)
                )
                response = await chat_stub.GetChatHistory(request)
            else:
                logger.error(f"Unknown chat method: {method}")
                return None
            
            return {
                "success": True,
                "data": response
            }
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC call to chat service failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error calling chat service: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def call_file_service(self, method: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Вызов метода сервиса файлов через gRPC"""
        try:
            # Получаем клиент для file сервиса
            file_stub = await self.create_grpc_client("file", "file-service:50053")
            
            # Выполняем вызов
            if method == "upload_file":
                request = pb2.UploadFileRequest(
                    filename=request_data.get("filename", ""),
                    content=request_data.get("content", b""),
                    uploader_id=request_data.get("uploader_id", 0),
                    chat_id=request_data.get("chat_id", ""),
                    visibility=request_data.get("visibility", "private")
                )
                response = await file_stub.UploadFile(request)
            elif method == "download_file":
                request = pb2.DownloadFileRequest(
                    file_id=request_data.get("file_id", "")
                )
                response = await file_stub.DownloadFile(request)
            elif method == "get_file_info":
                request = pb2.GetFileInfoRequest(
                    file_id=request_data.get("file_id", "")
                )
                response = await file_stub.GetFileInfo(request)
            else:
                logger.error(f"Unknown file method: {method}")
                return None
            
            return {
                "success": True,
                "data": response
            }
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC call to file service failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error calling file service: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def call_notification_service(self, method: str, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Вызов метода сервиса уведомлений через gRPC"""
        try:
            # Получаем клиент для notification сервиса
            notification_stub = await self.create_grpc_client("notification", "notification-service:50054")
            
            # Выполняем вызов
            if method == "send_notification":
                request = pb2.SendNotificationRequest(
                    user_id=request_data.get("user_id", 0),
                    type=request_data.get("type", "message"),
                    title=request_data.get("title", ""),
                    content=request_data.get("content", ""),
                    channels=request_data.get("channels", ["push"]),
                    priority=request_data.get("priority", "medium")
                )
                response = await notification_stub.SendNotification(request)
            elif method == "get_user_notifications":
                request = pb2.GetUserNotificationsRequest(
                    user_id=request_data.get("user_id", 0),
                    limit=request_data.get("limit", 50),
                    offset=request_data.get("offset", 0)
                )
                response = await notification_stub.GetUserNotifications(request)
            elif method == "mark_as_read":
                request = pb2.MarkAsReadRequest(
                    notification_id=request_data.get("notification_id", ""),
                    user_id=request_data.get("user_id", 0)
                )
                response = await notification_stub.MarkAsRead(request)
            else:
                logger.error(f"Unknown notification method: {method}")
                return None
            
            return {
                "success": True,
                "data": response
            }
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC call to notification service failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error calling notification service: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def requires_moderation(self, content_type: ContentType) -> bool:
        """Проверка, требует ли контент модерации"""
        # В реальной системе здесь будет более сложная логика
        # в зависимости от типа контента, пользователя и т.д.
        return content_type in [ContentType.IMAGE, ContentType.VIDEO, ContentType.LINK]

    async def _submit_for_moderation(self, content: Content):
        """Отправка контента на модерацию"""
        moderation_record = ContentModeration(
            id=str(uuid.uuid4()),
            content_id=content.id,
            moderator_id=None,  # Будет назначен системой
            status=ContentModerationStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO content_moderation (
                    id, content_id, moderator_id, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                moderation_record.id, moderation_record.content_id,
                moderation_record.moderator_id, moderation_record.status.value,
                moderation_record.created_at, moderation_record.updated_at
            )

    async def _schedule_content_publish(self, content: Content):
        """Планирование публикации контента"""
        if not content.scheduled_publish:
            return

        # Добавляем в очередь планировщика
        await redis_client.zadd(
            "scheduled_content_queue",
            {content.id: content.scheduled_publish.timestamp()}
        )

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальной системе здесь будет проверка прав пользователя
        return False

# Глобальный экземпляр для использования в приложении
grpc_communication_service = GRPCCommunicationService()