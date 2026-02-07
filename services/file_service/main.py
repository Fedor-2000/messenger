# File Service
# File: services/file_service/main.py

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

import aiohttp
from aiohttp import web, MultipartReader
import asyncpg
import redis.asyncio as redis
from PIL import Image
import aiofiles
from pydantic import BaseModel

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    DB_URL = os.getenv('DB_URL', 'postgresql://messenger:password@db:5432/messenger')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')
    UPLOAD_DIR = os.getenv('UPLOAD_DIR', '/app/uploads')
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '50*1024*1024'))  # 50MB

config = Config()

# Глобальные переменные
db_pool = None
redis_client = None

class FileUpload(BaseModel):
    filename: str
    stored_name: str
    uploader_id: int
    size: int
    mime_type: str
    chat_id: str

class FileService:
    def __init__(self):
        # Создаем директорию для загрузки файлов
        Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    async def upload_file(self, file_data: bytes, filename: str, uploader_id: int, chat_id: str) -> Optional[Dict]:
        """Загрузка файла"""
        # Проверяем размер файла
        if len(file_data) > config.MAX_FILE_SIZE:
            return None
        
        # Генерируем уникальное имя файла
        file_ext = Path(filename).suffix
        stored_name = f"{uuid.uuid4()}{file_ext}"
        file_path = Path(config.UPLOAD_DIR) / stored_name
        
        # Сохраняем файл
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
        
        # Определяем MIME тип
        mime_type = self._get_mime_type(file_ext)
        
        # Сохраняем информацию о файле в базе данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                INSERT INTO files (
                    filename, stored_name, uploader_id, size, mime_type, uploaded_at, chat_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, filename, stored_name, uploader_id, size, mime_type, uploaded_at
                ''',
                filename, stored_name, uploader_id, len(file_data), mime_type, 
                datetime.utcnow(), chat_id
            )
        
        file_info = {
            'id': row['id'],
            'filename': row['filename'],
            'stored_name': row['stored_name'],
            'uploader_id': row['uploader_id'],
            'size': row['size'],
            'mime_type': row['mime_type'],
            'uploaded_at': row['uploaded_at'].isoformat(),
            'download_url': f"/files/download/{row['stored_name']}"
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

    def _get_mime_type(self, ext: str) -> str:
        """Определение MIME типа по расширению"""
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.txt': 'text/plain',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime'
        }
        return mime_types.get(ext.lower(), 'application/octet-stream')

    async def download_file(self, stored_name: str) -> Optional[bytes]:
        """Загрузка файла"""
        file_path = Path(config.UPLOAD_DIR) / stored_name
        
        if not file_path.exists():
            return None
        
        async with aiofiles.open(file_path, 'rb') as f:
            return await f.read()

    async def get_file_info(self, file_id: int) -> Optional[Dict]:
        """Получение информации о файле"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''
                SELECT id, filename, stored_name, uploader_id, size, mime_type, uploaded_at, chat_id
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
            'chat_id': row['chat_id']
        }

    async def process_image(self, stored_name: str, width: int = None, height: int = None) -> Optional[str]:
        """Обработка изображения (изменение размера)"""
        file_path = Path(config.UPLOAD_DIR) / stored_name
        
        if not file_path.exists():
            return None
        
        # Проверяем, является ли файл изображением
        if not self._is_image(file_path.suffix):
            return None
        
        try:
            # Открываем изображение
            async with aiofiles.open(file_path, 'rb') as f:
                img_data = await f.read()
            
            # Создаем изображение из байтов
            import io
            img = Image.open(io.BytesIO(img_data))
            
            # Изменяем размер
            if width and height:
                img = img.resize((width, height))
            elif width:
                w_percent = width / float(img.size[0])
                height = int(float(img.size[1]) * w_percent)
                img = img.resize((width, height))
            elif height:
                h_percent = height / float(img.size[1])
                width = int(float(img.size[0]) * h_percent)
                img = img.resize((width, height))
            
            # Генерируем новое имя для обработанного изображения
            processed_name = f"processed_{stored_name}"
            processed_path = Path(config.UPLOAD_DIR) / processed_name
            
            # Сохраняем обработанное изображение
            img.save(processed_path, format=img.format)
            
            return processed_name
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return None

    def _is_image(self, ext: str) -> bool:
        """Проверка, является ли файл изображением"""
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']
        return ext.lower() in image_exts

    async def create_streaming_url(self, stored_name: str, duration: int = 3600) -> Optional[str]:
        """Создание URL для прямого эфира/стриминга"""
        # Генерируем временный токен для доступа к файлу
        temp_token = str(uuid.uuid4())
        temp_key = f"stream_token:{temp_token}"
        
        # Сохраняем сведения о файле и токене в Redis с TTL
        await redis_client.setex(temp_key, duration, stored_name)
        
        return f"/files/stream/{temp_token}"

    async def get_streaming_file(self, temp_token: str) -> Optional[bytes]:
        """Получение файла по временному токену (для стриминга)"""
        temp_key = f"stream_token:{temp_token}"
        stored_name = await redis_client.get(temp_key)
        
        if not stored_name:
            return None
        
        # Продлеваем токен на 5 минут для продолжения стриминга
        await redis_client.expire(temp_key, 300)
        
        return await self.download_file(stored_name)

# Инициализация сервиса
file_service = FileService()

async def upload_handler(request):
    """Обработчик загрузки файла"""
    if request.content_type.startswith('multipart/'):
        reader = MultipartReader.from_response(request)
        
        # Получаем файл и метаданные
        field = await reader.next()
        if field.name != 'file':
            return web.json_response({'error': 'Expected file field named "file"'}, status=400)
        
        filename = field.filename
        file_data = await field.read(decode=False)
        
        # Получаем метаданные из других полей
        uploader_id = None
        chat_id = None
        
        while True:
            field = await reader.next()
            if field is None:
                break
            if field.name == 'uploader_id':
                uploader_id = int(await field.read(decode=False))
            elif field.name == 'chat_id':
                chat_id = await field.read(decode=False)
        
        if not all([filename, uploader_id, chat_id]):
            return web.json_response({'error': 'Missing required fields'}, status=400)
        
        result = await file_service.upload_file(file_data, filename, uploader_id, chat_id)
        
        if result:
            return web.json_response(result, status=201)
        else:
            return web.json_response({'error': 'File upload failed'}, status=400)
    else:
        # Прямая загрузка файла
        filename = request.headers.get('X-File-Name')
        uploader_id = int(request.headers.get('X-Uploader-ID', 0))
        chat_id = request.headers.get('X-Chat-ID')
        
        if not all([filename, uploader_id, chat_id]):
            return web.json_response({'error': 'Missing required headers'}, status=400)
        
        file_data = await request.read()
        result = await file_service.upload_file(file_data, filename, uploader_id, chat_id)
        
        if result:
            return web.json_response(result, status=201)
        else:
            return web.json_response({'error': 'File upload failed'}, status=400)

async def download_handler(request):
    """Обработчик скачивания файла"""
    stored_name = request.match_info['stored_name']
    
    file_data = await file_service.download_file(stored_name)
    
    if file_data:
        file_info = await file_service.get_file_info_by_stored_name(stored_name)
        return web.Response(body=file_data, content_type=file_info['mime_type'])
    else:
        return web.Response(status=404, text='File not found')

async def get_file_info_handler(request):
    """Обработчик получения информации о файле"""
    file_id = int(request.match_info['file_id'])
    
    info = await file_service.get_file_info(file_id)
    
    if info:
        return web.json_response(info)
    else:
        return web.Response(status=404, text='File not found')

async def process_image_handler(request):
    """Обработчик обработки изображения"""
    stored_name = request.match_info['stored_name']
    width = request.query.get('width')
    height = request.query.get('height')
    
    if width:
        width = int(width)
    if height:
        height = int(height)
    
    processed_name = await file_service.process_image(stored_name, width, height)
    
    if processed_name:
        return web.json_response({'processed_file': processed_name})
    else:
        return web.Response(status=400, text='Image processing failed')

async def create_streaming_handler(request):
    """Обработчик создания URL для стриминга"""
    data = await request.json()
    stored_name = data.get('stored_name')
    duration = data.get('duration', 3600)  # по умолчанию 1 час
    
    if not stored_name:
        return web.json_response({'error': 'Missing stored_name'}, status=400)
    
    streaming_url = await file_service.create_streaming_url(stored_name, duration)
    
    if streaming_url:
        return web.json_response({'streaming_url': streaming_url})
    else:
        return web.Response(status=400, text='Failed to create streaming URL')

async def stream_handler(request):
    """Обработчик стриминга файла"""
    temp_token = request.match_info['temp_token']
    
    file_data = await file_service.get_streaming_file(temp_token)
    
    if file_data:
        # Определяем MIME тип по токену (нужно хранить в Redis вместе с именем файла)
        stored_name = await redis_client.get(f"stream_token:{temp_token}")
        file_info = await file_service.get_file_info_by_stored_name(stored_name)
        
        return web.Response(
            body=file_data, 
            content_type=file_info['mime_type'],
            headers={'Cache-Control': 'no-cache'}
        )
    else:
        return web.Response(status=404, text='Stream not found or expired')

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({'status': 'healthy'})

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/upload', upload_handler)
    app.router.add_get('/download/{stored_name}', download_handler)
    app.router.add_get('/files/{file_id}', get_file_info_handler)
    app.router.add_post('/process/image/{stored_name}', process_image_handler)
    app.router.add_post('/stream', create_streaming_handler)
    app.router.add_get('/stream/{temp_token}', stream_handler)
    app.router.add_get('/health', health_check)
    
    return app

async def file_service.get_file_info_by_stored_name(self, stored_name: str) -> Optional[Dict]:
    """Вспомогательный метод для получения информации о файле по stored_name"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT id, filename, stored_name, uploader_id, size, mime_type, uploaded_at, chat_id
            FROM files WHERE stored_name = $1
            ''',
            stored_name
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
        'chat_id': row['chat_id']
    }

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
    
    site = web.TCPSite(runner, '0.0.0.0', 8002)
    await site.start()
    
    logger.info("File Service запущен на порту 8002")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())