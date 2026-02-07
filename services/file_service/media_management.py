# File and Media Management System
# File: services/file_service/media_management.py

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
import aiofiles
import aiohttp
from PIL import Image
import hashlib
import mimetypes
from urllib.parse import urlparse

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

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

class MediaProcessingJobStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class FileMetadata(BaseModel):
    id: str
    filename: str
    original_filename: str
    stored_name: str
    file_type: FileType
    mime_type: str
    size: int
    checksum: str
    dimensions: Optional[Dict[str, int]] = None  # Для изображений и видео
    duration: Optional[float] = None  # Для аудио и видео
    bitrate: Optional[int] = None  # Для аудио
    frame_rate: Optional[float] = None  # Для видео
    user_id: int
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    status: FileStatus
    upload_url: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    processed_files: List[Dict[str, Any]] = []  # [{'type': 'thumbnail', 'url': 'url', 'size': 'small'}]
    tags: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    uploaded_at: datetime = None
    processed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

class MediaProcessingJob(BaseModel):
    id: str
    file_id: str
    user_id: int
    job_type: str  # 'thumbnail', 'transcode', 'extract_audio', 'watermark', etc.
    status: MediaProcessingJobStatus
    input_params: Dict[str, Any]
    output_params: Optional[Dict[str, Any]] = None
    progress: float = 0.0
    error_message: Optional[str] = None
    started_at: datetime = None
    completed_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

class MediaManagementService:
    def __init__(self):
        self.upload_dir = Path("/app/uploads/media")
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

    async def upload_file(self, file_data: bytes, original_filename: str, user_id: int,
                         chat_id: Optional[str] = None, group_id: Optional[str] = None,
                         project_id: Optional[str] = None, tags: Optional[List[str]] = None,
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """Загрузка файла"""
        # Проверяем размер файла
        if len(file_data) > self.max_file_size:
            logger.error(f"File too large: {len(file_data)} bytes")
            return None

        # Определяем тип файла
        file_extension = Path(original_filename).suffix.lower()
        file_type = self._get_file_type(file_extension)
        mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'

        # Генерируем уникальное имя файла
        stored_name = f"{uuid.uuid4()}{file_extension}"
        file_path = self.upload_dir / stored_name

        # Сохраняем файл
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)

        # Вычисляем контрольную сумму
        checksum = hashlib.md5(file_data).hexdigest()

        # Получаем метаданные файла
        file_stat = os.stat(file_path)
        size = file_stat.st_size

        # Для изображений и видео получаем дополнительные метаданные
        dimensions = None
        duration = None
        bitrate = None
        frame_rate = None

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
                dimensions = {"width": 1920, "height": 1080}  # Заглушка
                duration = 120.5  # Заглушка
                frame_rate = 30.0  # Заглушка
            elif file_type == FileType.AUDIO:
                duration = 240.0  # Заглушка
                bitrate = 320  # Заглушка

        file_id = str(uuid.uuid4())

        file_metadata = FileMetadata(
            id=file_id,
            filename=original_filename,
            original_filename=original_filename,
            stored_name=stored_name,
            file_type=file_type,
            mime_type=mime_type,
            size=size,
            checksum=checksum,
            dimensions=dimensions,
            duration=duration,
            bitrate=bitrate,
            frame_rate=frame_rate,
            user_id=user_id,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            status=FileStatus.UPLOADED,
            download_url=f"/files/download/{stored_name}",
            thumbnail_url=None,  # Будет установлено после обработки
            processed_files=[],
            tags=tags or [],
            metadata=metadata or {},
            uploaded_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем метаданные файла в базу данных
        await self._save_file_metadata(file_metadata)

        # Добавляем в кэш
        await self._cache_file_metadata(file_metadata)

        # Создаем задание на обработку файла (например, создание миниатюр)
        await self._create_processing_jobs(file_metadata)

        # Уведомляем заинтересованные стороны
        await self._notify_file_uploaded(file_metadata)

        return file_id

    async def _save_file_metadata(self, file_metadata: FileMetadata):
        """Сохранение метаданных файла в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO files (
                    id, filename, original_filename, stored_name, file_type, mime_type,
                    size, checksum, dimensions, duration, bitrate, frame_rate,
                    user_id, chat_id, group_id, project_id, status, upload_url,
                    download_url, thumbnail_url, processed_files, tags, metadata,
                    uploaded_at, processed_at, expires_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                         $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25,
                         $26, $27, $28)
                """,
                file_metadata.id, file_metadata.filename, file_metadata.original_filename,
                file_metadata.stored_name, file_metadata.file_type.value,
                file_metadata.mime_type, file_metadata.size, file_metadata.checksum,
                json.dumps(file_metadata.dimensions) if file_metadata.dimensions else None,
                file_metadata.duration, file_metadata.bitrate, file_metadata.frame_rate,
                file_metadata.user_id, file_metadata.chat_id, file_metadata.group_id,
                file_metadata.project_id, file_metadata.status.value,
                file_metadata.upload_url, file_metadata.download_url,
                file_metadata.thumbnail_url,
                json.dumps(file_metadata.processed_files) if file_metadata.processed_files else None,
                file_metadata.tags, json.dumps(file_metadata.metadata) if file_metadata.metadata else None,
                file_metadata.uploaded_at, file_metadata.processed_at,
                file_metadata.expires_at, file_metadata.created_at, file_metadata.updated_at
            )

    async def get_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Получение метаданных файла"""
        # Сначала проверяем кэш
        cached_metadata = await self._get_cached_file_metadata(file_id)
        if cached_metadata:
            return cached_metadata

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, filename, original_filename, stored_name, file_type, mime_type,
                       size, checksum, dimensions, duration, bitrate, frame_rate,
                       user_id, chat_id, group_id, project_id, status, upload_url,
                       download_url, thumbnail_url, processed_files, tags, metadata,
                       uploaded_at, processed_at, expires_at, created_at, updated_at
                FROM files WHERE id = $1
                """,
                file_id
            )

        if not row:
            return None

        file_metadata = FileMetadata(
            id=row['id'],
            filename=row['filename'],
            original_filename=row['original_filename'],
            stored_name=row['stored_name'],
            file_type=FileType(row['file_type']),
            mime_type=row['mime_type'],
            size=row['size'],
            checksum=row['checksum'],
            dimensions=json.loads(row['dimensions']) if row['dimensions'] else None,
            duration=row['duration'],
            bitrate=row['bitrate'],
            frame_rate=row['frame_rate'],
            user_id=row['user_id'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            status=FileStatus(row['status']),
            upload_url=row['upload_url'],
            download_url=row['download_url'],
            thumbnail_url=row['thumbnail_url'],
            processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
            tags=row['tags'] or [],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            uploaded_at=row['uploaded_at'],
            processed_at=row['processed_at'],
            expires_at=row['expires_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем метаданные
        await self._cache_file_metadata(file_metadata)

        return file_metadata

    async def download_file(self, file_id: str) -> Optional[Tuple[bytes, str]]:
        """Скачивание файла"""
        file_metadata = await self.get_file_metadata(file_id)
        if not file_metadata:
            return None

        file_path = self.upload_dir / file_metadata.stored_name
        if not file_path.exists():
            return None

        async with aiofiles.open(file_path, 'rb') as f:
            file_data = await f.read()

        return file_data, file_metadata.mime_type

    async def delete_file(self, file_id: str, user_id: int) -> bool:
        """Удаление файла"""
        file_metadata = await self.get_file_metadata(file_id)
        if not file_metadata:
            return False

        # Проверяем права на удаление
        if file_metadata.user_id != user_id:
            return False

        # Удаляем файл с диска
        file_path = self.upload_dir / file_metadata.stored_name
        if file_path.exists():
            file_path.unlink()

        # Удаляем миниатюры
        for processed_file in file_metadata.processed_files:
            if processed_file.get('type') == 'thumbnail':
                thumb_path = self.thumbnail_dir / processed_file.get('stored_name', '')
                if thumb_path.exists():
                    thumb_path.unlink()

        # Удаляем из базы данных
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM files WHERE id = $1", file_id)

        # Удаляем из кэша
        await self._uncache_file_metadata(file_id)

        # Удаляем связанные задания на обработку
        await self._delete_processing_jobs(file_id)

        # Уведомляем заинтересованные стороны
        await self._notify_file_deleted(file_metadata)

        return True

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
            "original_stored_name": file_metadata.stored_name
        }

        job_id = await self._create_processing_job(
            file_id, file_metadata.user_id, "thumbnail", job_input_params
        )

        if job_id:
            # Обновляем статус файла
            file_metadata.status = FileStatus.PROCESSING
            await self._update_file_metadata(file_metadata)

        return job_id

    async def transcode_media(self, file_id: str, target_format: str, 
                             quality: str = "medium") -> Optional[str]:
        """Конвертация медиафайла в другой формат"""
        file_metadata = await self.get_file_metadata(file_id)
        if not file_metadata:
            return None

        if file_metadata.file_type not in [FileType.IMAGE, FileType.VIDEO, FileType.AUDIO]:
            return None

        # Создаем задание на перекодировку
        job_input_params = {
            "file_id": file_id,
            "target_format": target_format,
            "quality": quality,
            "original_stored_name": file_metadata.stored_name
        }

        job_id = await self._create_processing_job(
            file_id, file_metadata.user_id, "transcode", job_input_params
        )

        if job_id:
            # Обновляем статус файла
            file_metadata.status = FileStatus.PROCESSING
            await self._update_file_metadata(file_metadata)

        return job_id

    async def _create_processing_job(self, file_id: str, user_id: int, job_type: str,
                                   input_params: Dict[str, Any]) -> Optional[str]:
        """Создание задания на обработку медиа"""
        job_id = str(uuid.uuid4())

        job = MediaProcessingJob(
            id=job_id,
            file_id=file_id,
            user_id=user_id,
            job_type=job_type,
            status=MediaProcessingJobStatus.PENDING,
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

    async def _save_processing_job(self, job: MediaProcessingJob):
        """Сохранение задания на обработку в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO media_processing_jobs (
                    id, file_id, user_id, job_type, status, input_params, output_params,
                    progress, error_message, started_at, completed_at, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                job.id, job.file_id, job.user_id, job.job_type, job.status.value,
                json.dumps(job.input_params), 
                json.dumps(job.output_params) if job.output_params else None,
                job.progress, job.error_message, job.started_at, job.completed_at,
                job.created_at, job.updated_at
            )

    async def _add_to_processing_queue(self, job: MediaProcessingJob):
        """Добавление задания в очередь обработки"""
        await redis_client.lpush("media_processing_queue", job.model_dump_json())

    async def _create_processing_jobs(self, file_metadata: FileMetadata):
        """Создание заданий на обработку файла"""
        # Для изображений создаем миниатюры
        if file_metadata.file_type == FileType.IMAGE:
            await self.create_thumbnail(file_metadata.id, "small")
            await self.create_thumbnail(file_metadata.id, "medium")
        # Для видео создаем миниатюру и возможно перекодировку
        elif file_metadata.file_type == FileType.VIDEO:
            await self.create_thumbnail(file_metadata.id, "medium")
            # Дополнительно можно создать задание на перекодировку для веба
            await self.transcode_media(file_metadata.id, "mp4", "web_optimized")

    async def process_next_job(self) -> bool:
        """Обработка следующего задания в очереди"""
        # Получаем следующее задание из очереди
        job_json = await redis_client.rpop("media_processing_queue")
        if not job_json:
            return False

        job_data = json.loads(job_json)
        job = MediaProcessingJob(**job_data)

        # Обновляем статус задания
        job.status = MediaProcessingJobStatus.IN_PROGRESS
        job.progress = 10.0  # Начальный прогресс
        await self._update_processing_job(job)

        try:
            # Выполняем обработку в зависимости от типа задания
            if job.job_type == "thumbnail":
                result = await self._process_thumbnail_job(job)
            elif job.job_type == "transcode":
                result = await self._process_transcode_job(job)
            else:
                result = {"success": False, "error": f"Unknown job type: {job.job_type}"}

            if result.get("success"):
                job.status = MediaProcessingJobStatus.COMPLETED
                job.progress = 100.0
                job.completed_at = datetime.utcnow()
                job.output_params = result.get("output_params", {})
                
                # Обновляем метаданные исходного файла
                await self._update_file_after_processing(job)
            else:
                job.status = MediaProcessingJobStatus.FAILED
                job.error_message = result.get("error", "Unknown error")
                job.progress = 100.0
                job.completed_at = datetime.utcnow()

        except Exception as e:
            job.status = MediaProcessingJobStatus.FAILED
            job.error_message = str(e)
            job.progress = 100.0
            job.completed_at = datetime.utcnow()
            logger.error(f"Error processing job {job.id}: {e}")

        # Обновляем задание в базе данных
        await self._update_processing_job(job)

        return True

    async def _process_thumbnail_job(self, job: MediaProcessingJob) -> Dict[str, Any]:
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

    async def _process_transcode_job(self, job: MediaProcessingJob) -> Dict[str, Any]:
        """Обработка задания на перекодировку медиа"""
        try:
            input_params = job.input_params
            file_id = input_params["file_id"]
            target_format = input_params["target_format"]
            quality = input_params["quality"]
            original_stored_name = input_params["original_stored_name"]

            # В реальной системе здесь будет использование FFmpeg или другой библиотеки
            # для перекодировки медиафайлов
            # Для упрощения возвращаем заглушку

            # Обновляем прогресс
            job.progress = 50.0
            await self._update_processing_job(job)

            # Генерируем имя для обработанного файла
            original_path = Path(original_stored_name)
            processed_name = f"processed_{quality}_{original_path.stem}.{target_format}"
            processed_path = self.processed_dir / processed_name

            # В реальной системе здесь будет фактическая перекодировка
            # Для упрощения просто копируем исходный файл
            original_full_path = self.upload_dir / original_stored_name
            if original_full_path.exists():
                import shutil
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
            logger.error(f"Error processing transcode job: {e}")
            return {"success": False, "error": str(e)}

    async def _update_processing_job(self, job: MediaProcessingJob):
        """Обновление задания на обработку в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE media_processing_jobs SET
                    status = $2, progress = $3, error_message = $4, completed_at = $5,
                    output_params = $6, updated_at = $7
                WHERE id = $1
                """,
                job.id, job.status.value, job.progress, job.error_message,
                job.completed_at, json.dumps(job.output_params) if job.output_params else None,
                job.updated_at
            )

    async def _update_file_after_processing(self, job: MediaProcessingJob):
        """Обновление файла после завершения обработки"""
        file_metadata = await self.get_file_metadata(job.file_id)
        if not file_metadata:
            return

        if job.job_type == "thumbnail" and job.status == MediaProcessingJobStatus.COMPLETED:
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

        elif job.job_type == "transcode" and job.status == MediaProcessingJobStatus.COMPLETED:
            # Добавляем перекодированный файл к файлу
            transcoded_info = {
                "type": "transcoded",
                "format": job.output_params.get("format", ""),
                "quality": job.output_params.get("quality", ""),
                "url": job.output_params.get("processed_url", ""),
                "stored_name": job.output_params.get("stored_name", ""),
                "created_at": datetime.utcnow().isoformat()
            }
            file_metadata.processed_files.append(transcoded_info)

        # Обновляем статус файла на "processed" если все задания завершены
        unfinished_jobs = await self._get_unfinished_jobs_for_file(job.file_id)
        if not unfinished_jobs:
            file_metadata.status = FileStatus.PROCESSED
            file_metadata.processed_at = datetime.utcnow()

        file_metadata.updated_at = datetime.utcnow()

        # Сохраняем обновленные метаданные
        await self._update_file_metadata(file_metadata)

    async def _update_file_metadata(self, file_metadata: FileMetadata):
        """Обновление метаданных файла в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE files SET
                    processed_files = $2, thumbnail_url = $3, status = $4,
                    processed_at = $5, updated_at = $6
                WHERE id = $1
                """,
                file_metadata.id,
                json.dumps(file_metadata.processed_files) if file_metadata.processed_files else None,
                file_metadata.thumbnail_url, file_metadata.status.value,
                file_metadata.processed_at, file_metadata.updated_at
            )

    async def _get_unfinished_jobs_for_file(self, file_id: str) -> List[MediaProcessingJob]:
        """Получение незавершенных заданий для файла"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, file_id, user_id, job_type, status, input_params, output_params,
                       progress, error_message, started_at, completed_at, created_at, updated_at
                FROM media_processing_jobs
                WHERE file_id = $1 AND status IN ('pending', 'in_progress')
                """,
                file_id
            )

        jobs = []
        for row in rows:
            job = MediaProcessingJob(
                id=row['id'],
                file_id=row['file_id'],
                user_id=row['user_id'],
                job_type=row['job_type'],
                status=MediaProcessingJobStatus(row['status']),
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

    async def _delete_processing_jobs(self, file_id: str):
        """Удаление заданий на обработку для файла"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM media_processing_jobs WHERE file_id = $1",
                file_id
            )

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

    async def _cache_file_metadata(self, file_metadata: FileMetadata):
        """Кэширование метаданных файла"""
        await redis_client.setex(f"file_metadata:{file_metadata.id}", 300, 
                                file_metadata.model_dump_json())

    async def _get_cached_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Получение метаданных файла из кэша"""
        cached = await redis_client.get(f"file_metadata:{file_id}")
        if cached:
            return FileMetadata(**json.loads(cached))
        return None

    async def _uncache_file_metadata(self, file_id: str):
        """Удаление метаданных файла из кэша"""
        await redis_client.delete(f"file_metadata:{file_id}")

    async def _notify_file_uploaded(self, file_metadata: FileMetadata):
        """Уведомление о загрузке файла"""
        notification = {
            'type': 'file_uploaded',
            'file_id': file_metadata.id,
            'filename': file_metadata.filename,
            'size': file_metadata.size,
            'mime_type': file_metadata.mime_type,
            'user_id': file_metadata.user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление в чат, если файл загружен в чат
        if file_metadata.chat_id:
            await self._send_notification_to_chat(file_metadata.chat_id, notification)

    async def _notify_file_deleted(self, file_metadata: FileMetadata):
        """Уведомление об удалении файла"""
        notification = {
            'type': 'file_deleted',
            'file_id': file_metadata.id,
            'filename': file_metadata.filename,
            'user_id': file_metadata.user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление в чат, если файл был в чате
        if file_metadata.chat_id:
            await self._send_notification_to_chat(file_metadata.chat_id, notification)

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:files"
        await redis_client.publish(channel, json.dumps(notification))

    async def get_user_files(self, user_id: int, file_type: Optional[FileType] = None,
                           limit: int = 50, offset: int = 0) -> List[FileMetadata]:
        """Получение файлов пользователя"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        if file_type:
            conditions.append(f"file_type = ${param_idx}")
            params.append(file_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, filename, original_filename, stored_name, file_type, mime_type,
                   size, checksum, dimensions, duration, bitrate, frame_rate,
                   user_id, chat_id, group_id, project_id, status, upload_url,
                   download_url, thumbnail_url, processed_files, tags, metadata,
                   uploaded_at, processed_at, expires_at, created_at, updated_at
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
            file_metadata = FileMetadata(
                id=row['id'],
                filename=row['filename'],
                original_filename=row['original_filename'],
                stored_name=row['stored_name'],
                file_type=FileType(row['file_type']),
                mime_type=row['mime_type'],
                size=row['size'],
                checksum=row['checksum'],
                dimensions=json.loads(row['dimensions']) if row['dimensions'] else None,
                duration=row['duration'],
                bitrate=row['bitrate'],
                frame_rate=row['frame_rate'],
                user_id=row['user_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                status=FileStatus(row['status']),
                upload_url=row['upload_url'],
                download_url=row['download_url'],
                thumbnail_url=row['thumbnail_url'],
                processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
                tags=row['tags'] or [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                uploaded_at=row['uploaded_at'],
                processed_at=row['processed_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            files.append(file_metadata)

        return files

    async def search_files(self, query: str, user_id: int,
                          file_types: Optional[List[FileType]] = None,
                          tags: Optional[List[str]] = None,
                          date_from: Optional[datetime] = None,
                          date_to: Optional[datetime] = None,
                          limit: int = 50, offset: int = 0) -> List[FileMetadata]:
        """Поиск файлов"""
        conditions = ["user_id = $1"]
        params = [user_id]
        param_idx = 2

        # Фильтр по типам файлов
        if file_types:
            type_values = [ft.value for ft in file_types]
            conditions.append(f"file_type = ANY(${'$'.join([str(i) for i in range(param_idx, param_idx + len(type_values))])})")
            params.extend(type_values)
            param_idx += len(type_values)

        # Фильтр по тегам
        if tags:
            for tag in tags:
                conditions.append(f"LOWER(${'$'.join([str(i) for i in range(param_idx, param_idx + len(tags))])}) = ANY(LOWER(tags))")
                params.extend(tags)
                param_idx += len(tags)

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
            conditions.append(f"LOWER(filename) LIKE LOWER(${'$'.join([str(i) for i in range(param_idx, param_idx + 1)])})")
            params.append(f'%{query}%')
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, filename, original_filename, stored_name, file_type, mime_type,
                   size, checksum, dimensions, duration, bitrate, frame_rate,
                   user_id, chat_id, group_id, project_id, status, upload_url,
                   download_url, thumbnail_url, processed_files, tags, metadata,
                   uploaded_at, processed_at, expires_at, created_at, updated_at
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
            file_metadata = FileMetadata(
                id=row['id'],
                filename=row['filename'],
                original_filename=row['original_filename'],
                stored_name=row['stored_name'],
                file_type=FileType(row['file_type']),
                mime_type=row['mime_type'],
                size=row['size'],
                checksum=row['checksum'],
                dimensions=json.loads(row['dimensions']) if row['dimensions'] else None,
                duration=row['duration'],
                bitrate=row['bitrate'],
                frame_rate=row['frame_rate'],
                user_id=row['user_id'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                status=FileStatus(row['status']),
                upload_url=row['upload_url'],
                download_url=row['download_url'],
                thumbnail_url=row['thumbnail_url'],
                processed_files=json.loads(row['processed_files']) if row['processed_files'] else [],
                tags=row['tags'] or [],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                uploaded_at=row['uploaded_at'],
                processed_at=row['processed_at'],
                expires_at=row['expires_at'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            files.append(file_metadata)

        return files

    async def get_file_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики по файлам пользователя"""
        async with db_pool.acquire() as conn:
            # Общая статистика
            total_files = await conn.fetchval(
                "SELECT COUNT(*) FROM files WHERE user_id = $1", user_id
            )
            
            total_size = await conn.fetchval(
                "SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = $1", user_id
            )
            
            # Статистика по типам файлов
            type_stats = await conn.fetch(
                """
                SELECT file_type, COUNT(*) as count, SUM(size) as total_size
                FROM files WHERE user_id = $1
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

# Глобальный экземпляр для использования в приложении
media_management_service = MediaManagementService()