# File Microservice
# File: services/file_microservice/main.py

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import hashlib
from pathlib import Path
import aiofiles
from PIL import Image
import magic  # python-magic для определения MIME типов
from urllib.parse import urlparse

import asyncpg
import redis.asyncio as redis
from aiohttp import web, MultipartReader
import boto3
from google.cloud import storage as gcs
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class FileType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    OTHER = "other"

class FileStatus(Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"
    DELETED = "deleted"

class FileVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    FRIENDS_ONLY = "friends_only"
    GROUP_MEMBERS = "group_members"
    PROJECT_MEMBERS = "project_members"

class FileProcessingType(Enum):
    THUMBNAIL_GENERATION = "thumbnail_generation"
    VIDEO_TRANSCODING = "video_transcoding"
    AUDIO_EXTRACTION = "audio_extraction"
    DOCUMENT_PREVIEW = "document_preview"
    VIRUS_SCAN = "virus_scan"
    OCR_PROCESSING = "ocr_processing"

class File(BaseModel):
    id: str
    original_filename: str
    stored_filename: str
    file_type: FileType
    mime_type: str
    size: int
    checksum: str
    uploader_id: int
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    status: FileStatus
    visibility: FileVisibility
    upload_url: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    processed_files: List[Dict] = []  # [{'type': 'thumbnail', 'url': 'url', 'size': 'small'}]
    metadata: Optional[Dict] = None
    uploaded_at: datetime = None
    processed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

class FileProcessingJob(BaseModel):
    id: str
    file_id: str
    user_id: int
    job_type: FileProcessingType
    status: str  # 'pending', 'in_progress', 'completed', 'failed'
    input_params: Dict[str, Any]
    output_params: Optional[Dict[str, Any]] = None
    progress: float = 0.0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

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
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_bucket = os.getenv('AWS_S3_BUCKET_NAME', 'messenger-files')
        
        if aws_access_key and aws_secret_key:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key
                )
                self.aws_bucket = aws_bucket
                logger.info("AWS S3 client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize AWS S3 client: {e}")
        
        # Google Cloud Storage
        gcs_bucket = os.getenv('GCS_BUCKET_NAME', 'messenger-files')
        gcs_project = os.getenv('GCS_PROJECT_ID')
        gcs_creds_path = os.getenv('GCS_CREDENTIALS_PATH')
        
        if gcs_creds_path:
            try:
                self.gcs_client = gcs.Client.from_service_account_json(gcs_creds_path)
                self.gcs_bucket = self.gcs_client.bucket(gcs_bucket)
                logger.info("Google Cloud Storage client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Storage client: {e}")
        
        # Azure Blob Storage
        azure_conn_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
        azure_container = os.getenv('AZURE_CONTAINER_NAME', 'messenger-files')
        
        if azure_conn_str:
            try:
                self.azure_client = BlobServiceClient.from_connection_string(azure_conn_str)
                self.azure_container = azure_container
                logger.info("Azure Blob Storage client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Blob Storage client: {e}")

    async def upload_to_s3(self, file_path: str, object_name: str) -> Optional[str]:
        """Загрузка файла в AWS S3"""
        if not self.s3_client:
            return None

        try:
            self.s3_client.upload_file(file_path, self.aws_bucket, object_name)
            # Возвращаем публичный URL
            url = f"https://{self.aws_bucket}.s3.amazonaws.com/{object_name}"
            return url
        except Exception as e:
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
            url = f"https://storage.googleapis.com/{self.gcs_bucket.name}/{object_name}"
            return url
        except Exception as e:
            logger.error(f"Error uploading to GCS: {e}")
            return None

    async def upload_to_azure(self, file_path: str, object_name: str) -> Optional[str]:
        """Загрузка файла в Azure Blob Storage"""
        if not self.azure_client:
            return None

        try:
            blob_client = self.azure_client.get_blob_client(
                container=self.azure_container,
                blob=object_name
            )
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            # Возвращаем публичный URL
            url = f"https://{self.azure_client.account_name}.blob.core.windows.net/{self.azure_container}/{object_name}"
            return url
        except Exception as e:
            logger.error(f"Error uploading to Azure: {e}")
            return None

    async def download_from_s3(self, object_name: str, local_path: str) -> bool:
        """Скачивание файла из AWS S3"""
        if not self.s3_client:
            return False

        try:
            self.s3_client.download_file(self.aws_bucket, object_name, local_path)
            return True
        except Exception as e:
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
            blob_client = self.azure_client.get_blob_client(
                container=self.azure_container,
                blob=object_name
            )
            with open(local_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            return True
        except Exception as e:
            logger.error(f"Error downloading from Azure: {e}")
            return False

class FileService:
    def __init__(self):
        self.upload_dir = Path("/app/uploads/files")
        self.thumbnail_dir = self.upload_dir / "thumbnails"
        self.processed_dir = self.upload_dir / "processed"
        
        # Создаем директории
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # Ограничения
        self.max_file_size = 100 * 1024 * 1024  # 100 MB
        self.max_thumbnail_size = 2 * 1024 * 1024  # 2 MB
        self.allowed_image_types = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
        self.allowed_video_types = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv'}
        self.allowed_audio_types = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'}
        self.allowed_document_types = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt'}
        
        # Менеджер облачных хранилищ
        self.cloud_manager = CloudStorageManager()

    async def upload_file(self, file_data: bytes, original_filename: str, uploader_id: int,
                         chat_id: Optional[str] = None, group_id: Optional[str] = None,
                         project_id: Optional[str] = None,
                         visibility: FileVisibility = FileVisibility.PRIVATE,
                         store_in_cloud: Optional[str] = None,
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """Загрузка файла"""
        # Проверяем размер файла
        if len(file_data) > self.max_file_size:
            logger.error(f"File too large: {len(file_data)} bytes")
            return None

        # Определяем тип файла
        file_extension = Path(original_filename).suffix.lower()
        file_type = self._get_file_type(file_extension)
        
        # Определяем MIME тип
        mime_type = magic.from_buffer(file_data, mime=True)

        # Генерируем уникальное имя файла
        stored_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = self.upload_dir / stored_filename

        # Сохраняем файл
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)

        # Вычисляем контрольную сумму
        checksum = hashlib.md5(file_data).hexdigest()

        # Получаем размер файла
        file_stat = await asyncio.get_event_loop().run_in_executor(None, os.stat, file_path)
        size = file_stat.st_size

        # Получаем метаданные файла
        dimensions = None
        duration = None
        bitrate = None

        if file_type == FileType.IMAGE:
            try:
                img = Image.open(file_path)
                dimensions = {"width": img.width, "height": img.height}
            except Exception as e:
                logger.error(f"Error getting image dimensions: {e}")
        elif file_type in [FileType.VIDEO, FileType.AUDIO]:
            # В реальной системе здесь будет использование библиотеки типа moviepy или ffprobe
            # Для упрощения возвращаем заглушки
            if file_type == FileType.VIDEO:
                dimensions = {"width": 1920, "height": 1080}
                duration = 120.5  # 2 минуты
            elif file_type == FileType.AUDIO:
                duration = 240.0  # 4 минуты
                bitrate = 320  # 320 kbps

        file_id = str(uuid.uuid4())

        file_obj = File(
            id=file_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_type=file_type,
            mime_type=mime_type,
            size=size,
            checksum=checksum,
            uploader_id=uploader_id,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            status=FileStatus.UPLOADED,
            visibility=visibility,
            upload_url=f"/files/upload/{stored_filename}",
            download_url=f"/files/download/{stored_filename}",
            thumbnail_url=None,  # Будет установлено после обработки
            processed_files=[],
            metadata=metadata or {},
            uploaded_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем файл в базу данных
        await self._save_file_to_db(file_obj)

        # Добавляем в кэш
        await self._cache_file(file_obj)

        # Если указано облачное хранилище, загружаем туда
        if store_in_cloud:
            cloud_url = await self._upload_to_cloud_storage(file_path, stored_filename, store_in_cloud)
            if cloud_url:
                file_obj.download_url = cloud_url
                await self._update_file_in_db(file_obj)

        # Создаем задания на обработку файла
        await self._create_processing_jobs(file_obj)

        # Уведомляем заинтересованные стороны
        await self._notify_file_uploaded(file_obj)

        # Создаем запись активности
        await self._log_activity(uploader_id, "file_uploaded", {
            "file_id": file_id,
            "filename": original_filename,
            "size": size,
            "type": file_type.value
        })

        return file_id

    async def _save_file_to_db(self, file: File):
        """Сохранение файла в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO files (
                    id, original_filename, stored_filename, file_type, mime_type,
                    size, checksum, uploader_id, chat_id, group_id, project_id,
                    status, visibility, upload_url, download_url, thumbnail_url,
                    processed_files, metadata, uploaded_at, processed_at, expires_at,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23)
                """,
                file.id, file.original_filename, file.stored_filename,
                file.file_type.value, file.mime_type, file.size, file.checksum,
                file.uploader_id, file.chat_id, file.group_id, file.project_id,
                file.status.value, file.visibility.value, file.upload_url,
                file.download_url, file.thumbnail_url,
                json.dumps(file.processed_files), json.dumps(file.metadata) if file.metadata else None,
                file.uploaded_at, file.processed_at, file.expires_at,
                file.created_at, file.updated_at
            )

    async def _upload_to_cloud_storage(self, file_path: Path, stored_name: str, 
                                     cloud_provider: str) -> Optional[str]:
        """Загрузка файла в облачное хранилище"""
        if cloud_provider == "aws_s3":
            return await self.cloud_manager.upload_to_s3(str(file_path), stored_name)
        elif cloud_provider == "gcs":
            return await self.cloud_manager.upload_to_gcs(str(file_path), stored_name)
        elif cloud_provider == "azure":
            return await self.cloud_manager.upload_to_azure(str(file_path), stored_name)
        else:
            return None

    async def download_file(self, file_id: str, user_id: Optional[int] = None) -> Optional[bytes]:
        """Скачивание файла"""
        file_metadata = await self.get_file_metadata(file_id)
        if not file_metadata:
            return None

        # Проверяем права доступа
        if not await self._can_access_file(file_metadata, user_id):
            return None

        # Проверяем, есть ли файл локально
        file_path = self.upload_dir / file_metadata.stored_filename
        if file_path.exists():
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()
        else:
            # Если файл не найден локально, пробуем скачать из облака
            if file_metadata.download_url and "cloud" in file_metadata.download_url:
                # В реальной системе здесь будет скачивание из облака
                # Для упрощения возвращаем None
                return None

        # Увеличиваем счетчик скачиваний
        await self._increment_download_count(file_id)

        # Создаем запись активности
        await self._log_activity(user_id, "file_downloaded", {
            "file_id": file_id,
            "filename": file_metadata.original_filename
        })

        return file_data

    async def get_file_metadata(self, file_id: str) -> Optional[File]:
        """Получение метаданных файла"""
        # Сначала проверяем кэш
        cached_file = await self._get_cached_file(file_id)
        if cached_file:
            return cached_file

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, original_filename, stored_filename, file_type, mime_type,
                       size, checksum, uploader_id, chat_id, group_id, project_id,
                       status, visibility, upload_url, download_url, thumbnail_url,
                       processed_files, metadata, uploaded_at, processed_at, expires_at,
                       created_at, updated_at
                FROM files WHERE id = $1
                """,
                file_id
            )

        if not row:
            return None

        file = File(
            id=row['id'],
            original_filename=row['original_filename'],
            stored_filename=row['stored_filename'],
            file_type=FileType(row['file_type']),
            mime_type=row['mime_type'],
            size=row['size'],
            checksum=row['checksum'],
            uploader_id=row['uploader_id'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            status=FileStatus(row['status']),
            visibility=FileVisibility(row['visibility']),
            upload_url=row['upload_url'],
            download_url=row['download_url'],
            thumbnail_url=row['thumbnail_url'],
            processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            uploaded_at=row['uploaded_at'],
            processed_at=row['processed_at'],
            expires_at=row['expires_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем файл
        await self._cache_file(file)

        return file

    async def create_thumbnail(self, file_id: str, size: str = "medium") -> Optional[str]:
        """Создание миниатюры для изображения или видео"""
        file_metadata = await self.get_file_metadata(file_id)
        if not file_metadata:
            return None

        if file_metadata.file_type not in [FileType.IMAGE, FileType.VIDEO]:
            return None

        # Создаем задание на создание миниатюры
        job_input_params = {
            "file_id": file_id,
            "size": size,
            "original_stored_name": file_metadata.stored_filename
        }

        job_id = await self._create_processing_job(
            file_id, file_metadata.uploader_id, FileProcessingType.THUMBNAIL_GENERATION, job_input_params
        )

        if job_id:
            # Обновляем статус файла
            file_metadata.status = FileStatus.PROCESSING
            await self._update_file_in_db(file_metadata)

        return job_id

    async def _create_processing_job(self, file_id: str, user_id: int, 
                                   job_type: FileProcessingType,
                                   input_params: Dict[str, Any]) -> Optional[str]:
        """Создание задания на обработку файла"""
        job_id = str(uuid.uuid4())

        job = FileProcessingJob(
            id=job_id,
            file_id=file_id,
            user_id=user_id,
            job_type=job_type,
            status="pending",
            input_params=input_params,
            progress=0.0,
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем задание в базу данных
        await self._save_processing_job(job)

        # Добавляем в очередь обработки
        await self._add_to_processing_queue(job)

        return job_id

    async def _save_processing_job(self, job: FileProcessingJob):
        """Сохранение задания на обработку в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO file_processing_jobs (
                    id, file_id, user_id, job_type, status, input_params, output_params,
                    progress, error_message, started_at, completed_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                job.id, job.file_id, job.user_id, job.job_type.value, job.status,
                json.dumps(job.input_params), 
                json.dumps(job.output_params) if job.output_params else None,
                job.progress, job.error_message, job.started_at, job.completed_at,
                job.created_at, job.updated_at
            )

    async def _add_to_processing_queue(self, job: FileProcessingJob):
        """Добавление задания в очередь обработки"""
        await redis_client.lpush("file_processing_queue", job.model_dump_json())

    async def process_next_file_job(self) -> bool:
        """Обработка следующего задания в очереди"""
        # Получаем следующее задание из очереди
        job_json = await redis_client.rpop("file_processing_queue")
        if not job_json:
            return False

        try:
            job_data = json.loads(job_json)
            job = FileProcessingJob(**job_data)

            # Обновляем статус задания
            job.status = "in_progress"
            job.progress = 10.0  # Начальный прогресс
            await self._update_processing_job(job)

            # Выполняем обработку в зависимости от типа задания
            if job.job_type == FileProcessingType.THUMBNAIL_GENERATION:
                result = await self._process_thumbnail_job(job)
            elif job.job_type == FileProcessingType.VIDEO_TRANSCODING:
                result = await self._process_video_transcoding_job(job)
            elif job.job_type == FileProcessingType.AUDIO_EXTRACTION:
                result = await self._process_audio_extraction_job(job)
            elif job.job_type == FileProcessingType.DOCUMENT_PREVIEW:
                result = await self._process_document_preview_job(job)
            elif job.job_type == FileProcessingType.VIRUS_SCAN:
                result = await self._process_virus_scan_job(job)
            elif job.job_type == FileProcessingType.OCR_PROCESSING:
                result = await self._process_ocr_job(job)
            else:
                result = {"success": False, "error": f"Unknown job type: {job.job_type}"}

            if result.get("success"):
                job.status = "completed"
                job.progress = 100.0
                job.completed_at = datetime.utcnow()
                job.output_params = result.get("output_params", {})
                
                # Обновляем метаданные исходного файла
                await self._update_file_after_processing(job)
            else:
                job.status = "failed"
                job.error_message = result.get("error", "Unknown error")
                job.progress = 100.0
                job.completed_at = datetime.utcnow()

            # Обновляем задание в базе данных
            await self._update_processing_job(job)

            return True
        except Exception as e:
            logger.error(f"Error processing file job: {e}")
            return False

    async def _process_thumbnail_job(self, job: FileProcessingJob) -> Dict[str, Any]:
        """Обработка задания на создание миниатюры"""
        try:
            input_params = job.input_params
            file_id = input_params["file_id"]
            size = input_params["size"]
            original_stored_name = input_params["original_stored_name"]

            # Получаем исходный файл
            original_path = self.upload_dir / original_stored_name
            if not original_path.exists():
                return {"success": False, "error": "Original file not found"}

            # Определяем размеры миниатюры
            size_map = {
                "small": (128, 128),
                "medium": (320, 240),
                "large": (640, 480)
            }
            target_size = size_map.get(size, size_map["medium"])

            # Открываем изображение
            img = Image.open(original_path)

            # Создаем миниатюру
            img.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Генерируем имя для миниатюры
            file_extension = original_path.suffix
            thumbnail_name = f"thumb_{size}_{original_path.stem}{file_extension}"
            thumbnail_path = self.thumbnail_dir / thumbnail_name

            # Сохраняем миниатюру
            img.save(thumbnail_path, optimize=True, quality=85)

            # Обновляем прогресс
            job.progress = 80.0
            await self._update_processing_job(job)

            # Возвращаем результат
            return {
                "success": True,
                "output_params": {
                    "thumbnail_path": str(thumbnail_path),
                    "thumbnail_url": f"/files/thumbnails/{thumbnail_name}",
                    "size": size,
                    "stored_name": thumbnail_name
                }
            }
        except Exception as e:
            logger.error(f"Error processing thumbnail job: {e}")
            return {"success": False, "error": str(e)}

    async def _process_video_transcoding_job(self, job: FileProcessingJob) -> Dict[str, Any]:
        """Обработка задания на перекодировку видео"""
        try:
            input_params = job.input_params
            file_id = input_params["file_id"]
            target_format = input_params.get("format", "mp4")
            quality = input_params.get("quality", "medium")

            # В реальной системе здесь будет использование FFmpeg или другой библиотеки
            # для перекодировки видео
            # Для упрощения возвращаем заглушку

            # Обновляем прогресс
            job.progress = 50.0
            await self._update_processing_job(job)

            # Генерируем имя для обработанного файла
            original_file = await self.get_file_metadata(file_id)
            if not original_file:
                return {"success": False, "error": "Original file not found"}

            original_path = Path(original_file.stored_filename)
            processed_name = f"transcoded_{quality}_{original_path.stem}.{target_format}"
            processed_path = self.processed_dir / processed_name

            # В реальной системе здесь будет фактическая перекодировка
            # Для упрощения просто копируем исходный файл
            import shutil
            original_full_path = self.upload_dir / original_file.stored_filename
            if original_full_path.exists():
                shutil.copy2(original_full_path, processed_path)

            # Обновляем прогресс
            job.progress = 90.0
            await self._update_processing_job(job)

            # Возвращаем результат
            return {
                "success": True,
                "output_params": {
                    "processed_path": str(processed_path),
                    "processed_url": f"/files/processed/{processed_name}",
                    "format": target_format,
                    "quality": quality,
                    "stored_name": processed_name
                }
            }
        except Exception as e:
            logger.error(f"Error processing video transcoding job: {e}")
            return {"success": False, "error": str(e)}

    async def _process_audio_extraction_job(self, job: FileProcessingJob) -> Dict[str, Any]:
        """Обработка задания на извлечение аудио"""
        try:
            input_params = job.input_params
            file_id = input_params["file_id"]

            # В реальной системе здесь будет извлечение аудио дорожки из видео
            # Для упрощения возвращаем заглушку

            # Обновляем прогресс
            job.progress = 60.0
            await self._update_processing_job(job)

            # Генерируем имя для аудио файла
            original_file = await self.get_file_metadata(file_id)
            if not original_file:
                return {"success": False, "error": "Original file not found"}

            original_path = Path(original_file.stored_filename)
            audio_name = f"extracted_audio_{original_path.stem}.mp3"
            audio_path = self.processed_dir / audio_name

            # В реальной системе здесь будет фактическое извлечение аудио
            # Для упрощения создаем пустой файл
            async with aiofiles.open(audio_path, 'w') as f:
                await f.write("")

            # Обновляем прогресс
            job.progress = 95.0
            await self._update_processing_job(job)

            # Возвращаем результат
            return {
                "success": True,
                "output_params": {
                    "audio_path": str(audio_path),
                    "audio_url": f"/files/audio/{audio_name}",
                    "stored_name": audio_name
                }
            }
        except Exception as e:
            logger.error(f"Error processing audio extraction job: {e}")
            return {"success": False, "error": str(e)}

    async def _update_file_after_processing(self, job: FileProcessingJob):
        """Обновление файла после завершения обработки"""
        file_metadata = await self.get_file_metadata(job.file_id)
        if not file_metadata:
            return

        if job.job_type == FileProcessingType.THUMBNAIL_GENERATION and job.status == "completed":
            # Добавляем миниатюру к файлу
            thumbnail_info = {
                "type": "thumbnail",
                "size": job.input_params.get("size", "medium"),
                "url": job.output_params.get("thumbnail_url", ""),
                "stored_name": job.output_params.get("stored_name", ""),
                "created_at": datetime.utcnow().isoformat()
            }
            file_metadata.processed_files.append(thumbnail_info)

            # Если это основная миниатюра, обновляем URL
            if job.input_params.get("size") == "medium":
                file_metadata.thumbnail_url = job.output_params.get("thumbnail_url", "")

        elif job.job_type in [FileProcessingType.VIDEO_TRANSCODING, FileProcessingType.AUDIO_EXTRACTION] and job.status == "completed":
            # Добавляем обработанный файл к файлу
            processed_info = {
                "type": job.job_type.value.replace("_", " ").title(),
                "format": job.output_params.get("format", ""),
                "quality": job.output_params.get("quality", ""),
                "url": job.output_params.get("processed_url", ""),
                "stored_name": job.output_params.get("stored_name", ""),
                "created_at": datetime.utcnow().isoformat()
            }
            file_metadata.processed_files.append(processed_info)

        # Обновляем статус файла на "processed" если все задания завершены
        unfinished_jobs = await self._get_unfinished_jobs_for_file(job.file_id)
        if not unfinished_jobs:
            file_metadata.status = FileStatus.PROCESSED
            file_metadata.processed_at = datetime.utcnow()

        file_metadata.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_file_in_db(file_metadata)

        # Обновляем в кэше
        await self._cache_file(file_metadata)

        # Уведомляем заинтересованные стороны
        await self._notify_file_processed(file_metadata)

    async def _get_unfinished_jobs_for_file(self, file_id: str) -> List[FileProcessingJob]:
        """Получение незавершенных заданий для файла"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, file_id, user_id, job_type, status, input_params, output_params,
                       progress, error_message, started_at, completed_at, created_at, updated_at
                FROM file_processing_jobs
                WHERE file_id = $1 AND status IN ('pending', 'in_progress')
                """,
                file_id
            )

        jobs = []
        for row in rows:
            job = FileProcessingJob(
                id=row['id'],
                file_id=row['file_id'],
                user_id=row['user_id'],
                job_type=FileProcessingType(row['job_type']),
                status=row['status'],
                input_params=json.loads(row['input_params']) if row['input_params'] else {},
                output_params=json.loads(row['output_params']) if row['output_params'] else None,
                progress=row['progress'],
                error_message=row['error_message'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            jobs.append(job)

        return jobs

    async def _update_file_in_db(self, file: File):
        """Обновление файла в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE files SET
                    status = $2, thumbnail_url = $3, processed_files = $4,
                    processed_at = $5, updated_at = $6
                WHERE id = $1
                """,
                file.id, file.status.value, file.thumbnail_url,
                json.dumps(file.processed_files), file.processed_at, file.updated_at
            )

    async def _cache_file(self, file: File):
        """Кэширование файла"""
        await redis_client.setex(f"file:{file.id}", 3600, file.model_dump_json())

    async def _get_cached_file(self, file_id: str) -> Optional[File]:
        """Получение файла из кэша"""
        cached = await redis_client.get(f"file:{file_id}")
        if cached:
            return File(**json.loads(cached.decode()))
        return None

    def _get_file_type(self, extension: str) -> FileType:
        """Определение типа файла по расширению"""
        if extension in self.allowed_image_types:
            return FileType.IMAGE
        elif extension in self.allowed_video_types:
            return FileType.VIDEO
        elif extension in self.allowed_audio_types:
            return FileType.AUDIO
        elif extension in self.allowed_document_types:
            return FileType.DOCUMENT
        elif extension in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
            return FileType.ARCHIVE
        else:
            return FileType.OTHER

    async def _can_access_file(self, file: File, user_id: Optional[int]) -> bool:
        """Проверка прав доступа к файлу"""
        if file.visibility == FileVisibility.PUBLIC:
            return True

        if not user_id:
            return False

        if file.uploader_id == user_id:
            return True

        if file.visibility == FileVisibility.FRIENDS_ONLY:
            return await self._are_friends(file.uploader_id, user_id)

        if file.visibility == FileVisibility.GROUP_MEMBERS:
            if file.group_id:
                return await self._is_group_member(user_id, file.group_id)

        if file.visibility == FileVisibility.PROJECT_MEMBERS:
            if file.project_id:
                return await self._is_project_member(user_id, file.project_id)

        return False

    async def _notify_file_uploaded(self, file: File):
        """Уведомление о загрузке файла"""
        notification = {
            'type': 'file_uploaded',
            'file': {
                'id': file.id,
                'original_filename': file.original_filename,
                'size': file.size,
                'mime_type': file.mime_type,
                'uploader_id': file.uploader_id
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем в чат, если файл загружен в чат
        if file.chat_id:
            await redis_client.publish(f"chat:{file.chat_id}:files", json.dumps(notification))

    async def _notify_file_processed(self, file: File):
        """Уведомление о завершении обработки файла"""
        notification = {
            'type': 'file_processed',
            'file_id': file.id,
            'processed_files_count': len(file.processed_files),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление загрузчику файла
        await redis_client.publish(f"user:{file.uploader_id}:files", json.dumps(notification))

        # Если файл связан с чатом, отправляем в чат
        if file.chat_id:
            await redis_client.publish(f"chat:{file.chat_id}:files", json.dumps(notification))

    async def _increment_download_count(self, file_id: str):
        """Увеличение счетчика скачиваний"""
        await redis_client.incr(f"file_downloads:{file_id}")

    async def _log_activity(self, user_id: int, action: str, details: Dict[str, Any]):
        """Логирование активности пользователя"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush(f"user_activities:{user_id}", json.dumps(activity))
        await redis_client.ltrim(f"user_activities:{user_id}", 0, 99)  # Храним последние 100 активностей

    async def get_user_files(self, user_id: int, file_type: Optional[FileType] = None,
                           visibility: Optional[FileVisibility] = None,
                           limit: int = 50, offset: int = 0) -> List[File]:
        """Получение файлов пользователя"""
        conditions = ["uploader_id = $1"]
        params = [user_id]
        param_idx = 2

        if file_type:
            conditions.append(f"file_type = ${param_idx}")
            params.append(file_type.value)
            param_idx += 1

        if visibility:
            conditions.append(f"visibility = ${param_idx}")
            params.append(visibility.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, original_filename, stored_filename, file_type, mime_type,
                   size, checksum, uploader_id, chat_id, group_id, project_id,
                   status, visibility, upload_url, download_url, thumbnail_url,
                   processed_files, metadata, uploaded_at, processed_at, expires_at,
                   created_at, updated_at
            FROM files
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        files = []
        for row in rows:
            file = File(
                id=row['id'],
                original_filename=row['original_filename'],
                stored_filename=row['stored_filename'],
                file_type=FileType(row['file_type']),
                mime_type=row['mime_type'],
                size=row['size'],
                checksum=row['checksum'],
                uploader_id=row['uploader_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                status=FileStatus(row['status']),
                visibility=FileVisibility(row['visibility']),
                upload_url=row['upload_url'],
                download_url=row['download_url'],
                thumbnail_url=row['thumbnail_url'],
                processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                uploaded_at=row['uploaded_at'],
                processed_at=row['processed_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            files.append(file)

        return files

    async def search_files(self, query: str, user_id: int,
                          file_types: Optional[List[FileType]] = None,
                          date_from: Optional[datetime] = None,
                          date_to: Optional[datetime] = None,
                          limit: int = 50, offset: int = 0) -> List[File]:
        """Поиск файлов"""
        conditions = ["(uploader_id = $1 OR visibility = 'public')"]
        params = [user_id]
        param_idx = 2

        # Фильтр по типам файлов
        if file_types:
            type_values = [ft.value for ft in file_types]
            conditions.append(f"file_type = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(type_values))])})")
            params.extend(type_values)
            param_idx += len(type_values)

        # Фильтр по дате
        if date_from:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(date_from)
            param_idx += 1

        if date_to:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(date_to)
            param_idx += 1

        # Фильтр по названию файла
        if query:
            conditions.append(f"original_filename ILIKE ${param_idx}")
            params.append(f"%{query}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, original_filename, stored_filename, file_type, mime_type,
                   size, checksum, uploader_id, chat_id, group_id, project_id,
                   status, visibility, upload_url, download_url, thumbnail_url,
                   processed_files, metadata, uploaded_at, processed_at, expires_at,
                   created_at, updated_at
            FROM files
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        files = []
        for row in rows:
            file = File(
                id=row['id'],
                original_filename=row['original_filename'],
                stored_filename=row['stored_filename'],
                file_type=FileType(row['file_type']),
                mime_type=row['mime_type'],
                size=row['size'],
                checksum=row['checksum'],
                uploader_id=row['uploader_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                status=FileStatus(row['status']),
                visibility=FileVisibility(row['visibility']),
                upload_url=row['upload_url'],
                download_url=row['download_url'],
                thumbnail_url=row['thumbnail_url'],
                processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                uploaded_at=row['uploaded_at'],
                processed_at=row['processed_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            files.append(file)

        return files

    async def get_file_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики по файлам пользователя"""
        async with db_pool.acquire() as conn:
            # Общая статистика
            total_files = await conn.fetchval(
                "SELECT COUNT(*) FROM files WHERE uploader_id = $1", user_id
            )
            
            total_size = await conn.fetchval(
                "SELECT COALESCE(SUM(size), 0) FROM files WHERE uploader_id = $1", user_id
            )
            
            # Статистика по типам файлов
            type_stats = await conn.fetch(
                """
                SELECT file_type, COUNT(*) as count, SUM(size) as total_size
                FROM files WHERE uploader_id = $1
                GROUP BY file_type
                """,
                user_id
            )

        stats = {
            "total_files": total_files or 0,
            "total_size_bytes": total_size or 0,
            "total_size_formatted": self._format_bytes(total_size or 0),
            "type_breakdown": [
                {
                    "type": row['file_type'],
                    "count": row['count'],
                    "size_bytes": row['total_size'] or 0,
                    "size_formatted": self._format_bytes(row['total_size'] or 0)
                }
                for row in type_stats
            ]
        }

        return stats

    def _format_bytes(self, bytes_value: int) -> str:
        """Форматирование байтов в человекочитаемый вид"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

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

    async def _is_project_member(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь участником проекта"""
        # В реальной системе здесь будет проверка в таблице участников проекта
        return False

    async def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        # В реальной системе здесь будет проверка прав пользователя
        return False

# Глобальный экземпляр для использования в приложении
file_service = FileService()