# Enhanced File Handling with Streaming and Cloud Storage
# File: services/file_service/enhanced_file_handling.py

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path

import aiofiles
import asyncpg
import redis.asyncio as redis
from PIL import Image
import boto3
from botocore.exceptions import ClientError
from google.cloud import storage as gcs
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)

# Конфигурация
class FileConfig:
    # Локальное хранилище
    LOCAL_UPLOAD_DIR = os.getenv('LOCAL_UPLOAD_DIR', '/app/uploads')
    
    # AWS S3
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME', 'messenger-files')
    AWS_S3_REGION = os.getenv('AWS_S3_REGION', 'us-east-1')
    
    # Google Cloud Storage
    GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'messenger-files-gcs')
    GCS_PROJECT_ID = os.getenv('GCS_PROJECT_ID')
    GCS_CREDENTIALS_PATH = os.getenv('GCS_CREDENTIALS_PATH')
    
    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'messenger-files')
    
    # Максимальный размер файла (50MB)
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '52428800'))
    
    # Поддерживаемые типы файлов
    ALLOWED_EXTENSIONS = {
        'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'},
        'document': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'},
        'video': {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'},
        'audio': {'.mp3', '.wav', '.flac', '.aac', '.ogg'},
        'archive': {'.zip', '.rar', '.7z', '.tar', '.gz'}
    }

config = FileConfig()

# Глобальные переменные
db_pool = None
redis_client = None

class CloudStorageManager:
    """Менеджер облачных хранилищ"""
    
    def __init__(self):
        self.s3_client = None
        self.gcs_client = None
        self.azure_client = None
        self._init_cloud_clients()
    
    def _init_cloud_clients(self):
        """Инициализация клиентов облачных хранилищ"""
        # AWS S3
        if config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                    region_name=config.AWS_S3_REGION
                )
                logger.info("AWS S3 client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize AWS S3 client: {e}")
        
        # Google Cloud Storage
        if config.GCS_CREDENTIALS_PATH:
            try:
                self.gcs_client = gcs.Client.from_service_account_json(config.GCS_CREDENTIALS_PATH)
                self.gcs_bucket = self.gcs_client.bucket(config.GCS_BUCKET_NAME)
                logger.info("Google Cloud Storage client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Storage client: {e}")
        
        # Azure Blob Storage
        if config.AZURE_STORAGE_CONNECTION_STRING:
            try:
                self.azure_client = BlobServiceClient.from_connection_string(config.AZURE_STORAGE_CONNECTION_STRING)
                logger.info("Azure Blob Storage client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Blob Storage client: {e}")
    
    async def upload_to_s3(self, file_path: str, object_name: str) -> Optional[str]:
        """Загрузка файла в AWS S3"""
        if not self.s3_client:
            return None
        
        try:
            self.s3_client.upload_file(file_path, config.AWS_S3_BUCKET_NAME, object_name)
            # Возвращаем публичный URL
            url = f"https://{config.AWS_S3_BUCKET_NAME}.s3.{config.AWS_S3_REGION}.amazonaws.com/{object_name}"
            return url
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            return None
    
    async def upload_to_gcs(self, file_path: str, object_name: str) -> Optional[str]:
        """Загрузка файла в Google Cloud Storage"""
        if not self.gcs_client:
            return None
        
        try:
            blob = self.gcs_bucket.blob(object_name)
            blob.upload_from_filename(file_path)
            # Возвращаем публичный URL
            url = f"https://storage.googleapis.com/{config.GCS_BUCKET_NAME}/{object_name}"
            return url
        except Exception as e:
            logger.error(f"Error uploading to GCS: {e}")
            return None
    
    async def upload_to_azure(self, file_path: str, object_name: str) -> Optional[str]:
        """Загрузка файла в Azure Blob Storage"""
        if not self.azure_client:
            return None
        
        try:
            container_client = self.azure_client.get_container_client(config.AZURE_CONTAINER_NAME)
            with open(file_path, "rb") as data:
                container_client.upload_blob(name=object_name, data=data, overwrite=True)
            # Возвращаем публичный URL
            url = f"https://{self.azure_client.account_name}.blob.core.windows.net/{config.AZURE_CONTAINER_NAME}/{object_name}"
            return url
        except Exception as e:
            logger.error(f"Error uploading to Azure: {e}")
            return None
    
    async def download_from_s3(self, object_name: str, local_path: str) -> bool:
        """Скачивание файла из AWS S3"""
        if not self.s3_client:
            return False
        
        try:
            self.s3_client.download_file(config.AWS_S3_BUCKET_NAME, object_name, local_path)
            return True
        except ClientError as e:
            logger.error(f"Error downloading from S3: {e}")
            return False
    
    async def download_from_gcs(self, object_name: str, local_path: str) -> bool:
        """Скачивание файла из Google Cloud Storage"""
        if not self.gcs_client:
            return False
        
        try:
            blob = self.gcs_bucket.blob(object_name)
            blob.download_to_filename(local_path)
            return True
        except Exception as e:
            logger.error(f"Error downloading from GCS: {e}")
            return False
    
    async def download_from_azure(self, object_name: str, local_path: str) -> bool:
        """Скачивание файла из Azure Blob Storage"""
        if not self.azure_client:
            return False
        
        try:
            blob_client = self.azure_client.get_blob_client(container=config.AZURE_CONTAINER_NAME, blob=object_name)
            with open(local_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            return True
        except Exception as e:
            logger.error(f"Error downloading from Azure: {e}")
            return False

class StreamingManager:
    """Менеджер потоковой передачи файлов"""
    
    def __init__(self):
        self.active_streams = {}
    
    async def create_streaming_session(self, file_id: str, user_id: int, duration: int = 3600) -> Optional[str]:
        """Создание сессии потоковой передачи"""
        session_id = f"stream_{file_id}_{uuid.uuid4()}"
        
        stream_info = {
            'file_id': file_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=duration)).isoformat(),
            'active': True
        }
        
        # Сохраняем сессию в Redis с TTL
        await redis_client.setex(f"stream_session:{session_id}", duration, json.dumps(stream_info))
        
        # Добавляем сессию к активным
        self.active_streams[session_id] = stream_info
        
        return session_id
    
    async def validate_stream_session(self, session_id: str) -> bool:
        """Проверка валидности сессии потоковой передачи"""
        stream_info_json = await redis_client.get(f"stream_session:{session_id}")
        if not stream_info_json:
            return False
        
        stream_info = json.loads(stream_info_json)
        if not stream_info.get('active', False):
            return False
        
        # Проверяем, не истекло ли время
        expires_at = datetime.fromisoformat(stream_info['expires_at'])
        if datetime.utcnow() > expires_at:
            await self.invalidate_stream_session(session_id)
            return False
        
        return True
    
    async def invalidate_stream_session(self, session_id: str):
        """Инвалидация сессии потоковой передачи"""
        await redis_client.delete(f"stream_session:{session_id}")
        if session_id in self.active_streams:
            del self.active_streams[session_id]

class EnhancedFileService:
    """Улучшенный сервис работы с файлами"""
    
    def __init__(self):
        self.cloud_manager = CloudStorageManager()
        self.streaming_manager = StreamingManager()
        
        # Создаем локальную директорию для загрузки файлов
        Path(config.LOCAL_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    
    async def upload_file(self, file_data: bytes, filename: str, uploader_id: int, 
                         chat_id: str, store_locally: bool = True, 
                         store_in_cloud: str = None) -> Optional[Dict]:
        """Загрузка файла с поддержкой облачных хранилищ"""
        # Проверяем размер файла
        if len(file_data) > config.MAX_FILE_SIZE:
            return None
        
        # Проверяем расширение файла
        file_ext = Path(filename).suffix.lower()
        file_type = self._get_file_type(file_ext)
        if not file_type:
            logger.warning(f"Unsupported file extension: {file_ext}")
            return None
        
        # Генерируем уникальное имя файла
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        local_file_path = Path(config.LOCAL_UPLOAD_DIR) / unique_filename
        
        # Сохраняем файл локально
        if store_locally:
            async with aiofiles.open(local_file_path, 'wb') as f:
                await f.write(file_data)
        
        # Определяем MIME тип
        mime_type = self._get_mime_type(file_ext)
        
        # Загружаем в облачное хранилище, если указано
        cloud_url = None
        if store_in_cloud:
            if store_in_cloud == 's3':
                cloud_url = await self.cloud_manager.upload_to_s3(str(local_file_path), unique_filename)
            elif store_in_cloud == 'gcs':
                cloud_url = await self.cloud_manager.upload_to_gcs(str(local_file_path), unique_filename)
            elif store_in_cloud == 'azure':
                cloud_url = await self.cloud_manager.upload_to_azure(str(local_file_path), unique_filename)
        
        # Сохраняем информацию о файле в базе данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO files (
                    filename, stored_name, uploader_id, size, mime_type, uploaded_at, chat_id, cloud_url
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, filename, stored_name, uploader_id, size, mime_type, uploaded_at, cloud_url
                ''',
                filename, unique_filename, uploader_id, len(file_data), mime_type, 
                datetime.utcnow(), chat_id, cloud_url
            )
        
        file_info = {
            'id': row['id'],
            'filename': row['filename'],
            'stored_name': row['stored_name'],
            'uploader_id': row['uploader_id'],
            'size': row['size'],
            'mime_type': row['mime_type'],
            'uploaded_at': row['uploaded_at'].isoformat(),
            'cloud_url': row['cloud_url'],
            'download_url': f"/files/download/{row['stored_name']}",
            'is_local': store_locally
        }
        
        # Отправляем уведомление о новом файле
        file_notification = {
            'type': 'file_uploaded',
            'file_info': file_info,
            'chat_id': chat_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await redis_client.publish(f"chat:{chat_id}", json.dumps(file_notification))
        
        return file_info
    
    async def download_file(self, stored_name: str, use_cache: bool = True) -> Optional[bytes]:
        """Загрузка файла с поддержкой кэширования"""
        # Проверяем кэш
        if use_cache:
            cached_file = await redis_client.get(f"file_cache:{stored_name}")
            if cached_file:
                return cached_file
        
        file_path = Path(config.LOCAL_UPLOAD_DIR) / stored_name
        
        # Если файл не найден локально, проверяем в облаке
        if not file_path.exists():
            # Получаем информацию о файле из базы данных
            async with db_pool.acquire() as conn:
                file_record = await conn.fetchrow(
                    '''
                    SELECT cloud_url FROM files WHERE stored_name = $1
                    ''',
                    stored_name
                )
            
            if file_record and file_record['cloud_url']:
                # Скачиваем файл из облака
                await self._download_from_cloud(stored_name)
        
        if file_path.exists():
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()
            
            # Кэшируем файл
            if use_cache:
                await redis_client.setex(f"file_cache:{stored_name}", 300, file_data)  # 5 минут
            
            return file_data
        
        return None
    
    async def _download_from_cloud(self, stored_name: str):
        """Скачивание файла из облачного хранилища"""
        async with db_pool.acquire() as conn:
            file_record = await conn.fetchrow(
                '''
                SELECT cloud_url FROM files WHERE stored_name = $1
                ''',
                stored_name
            )
        
        if not file_record or not file_record['cloud_url']:
            return False
        
        # Определяем, из какого облака скачать
        cloud_url = file_record['cloud_url']
        file_path = Path(config.LOCAL_UPLOAD_DIR) / stored_name
        
        if 'amazonaws.com' in cloud_url:
            # AWS S3
            object_name = stored_name
            return await self.cloud_manager.download_from_s3(object_name, str(file_path))
        elif 'googleapis.com' in cloud_url:
            # Google Cloud Storage
            object_name = stored_name
            return await self.cloud_manager.download_from_gcs(object_name, str(file_path))
        elif 'windows.net' in cloud_url:
            # Azure Blob Storage
            object_name = stored_name
            return await self.cloud_manager.download_from_azure(object_name, str(file_path))
        
        return False
    
    async def get_file_info(self, file_id: int) -> Optional[Dict]:
        """Получение информации о файле"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT id, filename, stored_name, uploader_id, size, mime_type, uploaded_at, chat_id, cloud_url
                FROM files WHERE id = $1
                ''',
                file_id
            )
        
        if not row:
            return None
        
        return {
            'id': row['id'],
            'filename': row['filename'],
            'stored_name': row['stored_name'],
            'uploader_id': row['uploader_id'],
            'size': row['size'],
            'mime_type': row['mime_type'],
            'uploaded_at': row['uploaded_at'].isoformat(),
            'chat_id': row['chat_id'],
            'cloud_url': row['cloud_url']
        }
    
    async def process_image(self, stored_name: str, width: int = None, height: int = None, 
                           quality: int = 85) -> Optional[str]:
        """Обработка изображения (изменение размера, сжатие)"""
        file_path = Path(config.LOCAL_UPLOAD_DIR) / stored_name
        
        if not file_path.exists() or not self._is_image(Path(stored_name).suffix):
            return None
        
        try:
            # Открываем изображение
            async with aiofiles.open(file_path, 'rb') as f:
                img_data = await f.read()
            
            from io import BytesIO
            img = Image.open(BytesIO(img_data))
            
            # Изменяем размер
            if width and height:
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            elif width:
                w_percent = width / float(img.size[0])
                height = int(float(img.size[1]) * w_percent)
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            elif height:
                h_percent = height / float(img.size[1])
                width = int(float(img.size[0]) * h_percent)
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            
            # Генерируем новое имя для обработанного изображения
            processed_name = f"processed_{stored_name}"
            processed_path = Path(config.LOCAL_UPLOAD_DIR) / processed_name
            
            # Сохраняем обработанное изображение
            img.save(processed_path, format=img.format, quality=quality, optimize=True)
            
            return processed_name
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return None
    
    async def create_streaming_url(self, stored_name: str, user_id: int, duration: int = 3600) -> Optional[str]:
        """Создание URL для потоковой передачи файла"""
        # Получаем информацию о файле
        async with db_pool.acquire() as conn:
            file_record = await conn.fetchrow(
                '''
                SELECT id FROM files WHERE stored_name = $1
                ''',
                stored_name
            )
        
        if not file_record:
            return None
        
        file_id = file_record['id']
        
        # Создаем сессию потоковой передачи
        session_id = await self.streaming_manager.create_streaming_session(file_id, user_id, duration)
        
        if not session_id:
            return None
        
        return f"/files/stream/{session_id}"
    
    async def get_streaming_file(self, session_id: str) -> Optional[bytes]:
        """Получение файла по сессии потоковой передачи"""
        # Проверяем валидность сессии
        is_valid = await self.streaming_manager.validate_stream_session(session_id)
        
        if not is_valid:
            return None
        
        # Получаем информацию о файле из сессии
        session_info_json = await redis_client.get(f"stream_session:{session_id}")
        if not session_info_json:
            return None
        
        session_info = json.loads(session_info_json)
        file_id = session_info['file_id']
        
        # Получаем stored_name из базы данных
        async with db_pool.acquire() as conn:
            file_record = await conn.fetchrow(
                '''
                SELECT stored_name FROM files WHERE id = $1
                ''',
                file_id
            )
        
        if not file_record:
            return None
        
        stored_name = file_record['stored_name']
        
        # Продлеваем сессию на 5 минут для продолжения потоковой передачи
        await redis_client.expire(f"stream_session:{session_id}", 300)
        
        return await self.download_file(stored_name)
    
    async def batch_upload(self, files_data: List[Dict], uploader_id: int, chat_id: str) -> List[Dict]:
        """Пакетная загрузка файлов"""
        results = []
        
        for file_info in files_data:
            file_data = file_info.get('data')
            filename = file_info.get('filename')
            store_in_cloud = file_info.get('store_in_cloud')
            
            result = await self.upload_file(
                file_data, filename, uploader_id, chat_id, 
                store_in_cloud=store_in_cloud
            )
            results.append(result)
        
        return results
    
    def _get_file_type(self, ext: str) -> Optional[str]:
        """Определение типа файла по расширению"""
        for file_type, extensions in config.ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
        return None
    
    def _get_mime_type(self, ext: str) -> str:
        """Определение MIME типа по расширению"""
        mime_types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.bmp': 'image/bmp', '.webp': 'image/webp',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.flac': 'audio/flac',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.wmv': 'video/x-ms-wmv',
            '.flv': 'video/x-flv',
            '.webm': 'video/webm'
        }
        return mime_types.get(ext.lower(), 'application/octet-stream')
    
    def _is_image(self, ext: str) -> bool:
        """Проверка, является ли файл изображением"""
        return ext.lower() in config.ALLOWED_EXTENSIONS['image']

# Глобальный экземпляр улучшенного сервиса файлов
enhanced_file_service = EnhancedFileService()

# Функции для использования в других частях приложения

async def upload_file_handler(file_data: bytes, filename: str, uploader_id: int, 
                            chat_id: str, store_in_cloud: str = None) -> Optional[Dict]:
    """Обработчик загрузки файла"""
    return await enhanced_file_service.upload_file(
        file_data, filename, uploader_id, chat_id, 
        store_in_cloud=store_in_cloud
    )

async def download_file_handler(stored_name: str) -> Optional[bytes]:
    """Обработчик скачивания файла"""
    return await enhanced_file_service.download_file(stored_name)

async def get_file_info_handler(file_id: int) -> Optional[Dict]:
    """Обработчик получения информации о файле"""
    return await enhanced_file_service.get_file_info(file_id)

async def process_image_handler(stored_name: str, width: int = None, height: int = None, 
                              quality: int = 85) -> Optional[str]:
    """Обработчик обработки изображения"""
    return await enhanced_file_service.process_image(stored_name, width, height, quality)

async def create_streaming_url_handler(stored_name: str, user_id: int, 
                                     duration: int = 3600) -> Optional[str]:
    """Обработчик создания URL для потоковой передачи"""
    return await enhanced_file_service.create_streaming_url(stored_name, user_id, duration)

async def get_streaming_file_handler(session_id: str) -> Optional[bytes]:
    """Обработчик получения файла по сессии потоковой передачи"""
    return await enhanced_file_service.get_streaming_file(session_id)

async def batch_upload_handler(files_data: List[Dict], uploader_id: int, 
                             chat_id: str) -> List[Dict]:
    """Обработчик пакетной загрузки файлов"""
    return await enhanced_file_service.batch_upload(files_data, uploader_id, chat_id)