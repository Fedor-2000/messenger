# AI Assistant System for Messenger
# File: services/ai_assistant/main.py

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Callable
from enum import Enum

import aiohttp
from aiohttp import web
import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Конфигурация
class AIAssistantConfig:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    HUGGINGFACE_API_KEY = os.getenv('HUGGINGFACE_API_KEY')
    
    # Модели для разных задач
    CHAT_MODEL = os.getenv('CHAT_MODEL', 'gpt-3.5-turbo')
    SUMMARIZATION_MODEL = os.getenv('SUMMARIZATION_MODEL', 'gpt-3.5-turbo')
    TRANSLATION_MODEL = os.getenv('TRANSLATION_MODEL', 'gpt-3.5-turbo')
    
    # Ограничения
    MAX_TOKENS = int(os.getenv('MAX_TOKENS', '2048'))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))

config = AIAssistantConfig()

# Глобальные переменные
db_pool = None
redis_client = None

class AssistantType(Enum):
    CHAT = "chat"
    SUMMARIZER = "summarizer"
    TRANSLATOR = "translator"
    ANALYZER = "analyzer"
    SCHEDULER = "scheduler"
    RESEARCHER = "researcher"

class AIAssistant(BaseModel):
    id: str
    name: str
    description: str
    type: AssistantType
    model: str
    enabled: bool = True
    created_at: datetime = None
    updated_at: datetime = None

class AIAssistantRequest(BaseModel):
    assistant_id: str
    user_id: int
    chat_id: str
    message: str
    context: Optional[Dict] = None
    options: Optional[Dict] = None

class AIAssistantResponse(BaseModel):
    assistant_id: str
    user_id: int
    chat_id: str
    request_message: str
    response_message: str
    timestamp: datetime = None
    latency: float = None

class AIAssistantService:
    def __init__(self):
        self.assistants = {}
        self.request_handlers = {
            AssistantType.CHAT: self.handle_chat_request,
            AssistantType.SUMMARIZER: self.handle_summarization_request,
            AssistantType.TRANSLATOR: self.handle_translation_request,
            AssistantType.ANALYZER: self.handle_analysis_request,
            AssistantType.SCHEDULER: self.handle_scheduling_request,
            AssistantType.RESEARCHER: self.handle_research_request
        }
        self.initialize_default_assistants()

    def initialize_default_assistants(self):
        """Инициализация встроенных ассистентов"""
        default_assistants = [
            AIAssistant(
                id="chatbot-001",
                name="Chat Assistant",
                description="Basic chat assistant for answering questions",
                type=AssistantType.CHAT,
                model=config.CHAT_MODEL
            ),
            AIAssistant(
                id="summarizer-001",
                name="Summarization Assistant",
                description="Summarizes long texts and documents",
                type=AssistantType.SUMMARIZER,
                model=config.SUMMARIZATION_MODEL
            ),
            AIAssistant(
                id="translator-001",
                name="Translation Assistant",
                description="Translates text between languages",
                type=AssistantType.TRANSLATOR,
                model=config.TRANSLATION_MODEL
            ),
            AIAssistant(
                id="analyzer-001",
                name="Analysis Assistant",
                description="Analyzes sentiment, keywords, and topics",
                type=AssistantType.ANALYZER,
                model=config.CHAT_MODEL
            )
        ]
        
        for assistant in default_assistants:
            self.assistants[assistant.id] = assistant

    async def create_custom_assistant(self, name: str, description: str, 
                                   assistant_type: AssistantType, 
                                   model: str, user_id: int) -> Optional[AIAssistant]:
        """Создание пользовательского ассистента"""
        assistant_id = f"custom-{user_id}-{datetime.utcnow().timestamp()}"
        
        assistant = AIAssistant(
            id=assistant_id,
            name=name,
            description=description,
            type=assistant_type,
            model=model,
            created_at=datetime.utcnow()
        )
        
        self.assistants[assistant_id] = assistant
        
        # Сохраняем в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO ai_assistants (
                    id, name, description, type, model, owner_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                assistant_id, name, description, assistant_type.value, 
                model, user_id, assistant.created_at
            )
        
        return assistant

    async def process_request(self, request: AIAssistantRequest) -> Optional[AIAssistantResponse]:
        """Обработка запроса к ассистенту"""
        if request.assistant_id not in self.assistants:
            return None
        
        assistant = self.assistants[request.assistant_id]
        if not assistant.enabled:
            return None
        
        start_time = datetime.utcnow()
        
        # Вызов соответствующего обработчика
        handler = self.request_handlers.get(assistant.type)
        if not handler:
            return None
        
        try:
            response_text = await handler(request)
            
            latency = (datetime.utcnow() - start_time).total_seconds()
            
            response = AIAssistantResponse(
                assistant_id=request.assistant_id,
                user_id=request.user_id,
                chat_id=request.chat_id,
                request_message=request.message,
                response_message=response_text,
                timestamp=datetime.utcnow(),
                latency=latency
            )
            
            # Сохраняем запрос и ответ
            await self.save_interaction(request, response)
            
            # Отправляем ответ в чат
            await self.send_response_to_chat(response)
            
            return response
        except Exception as e:
            logger.error(f"Error processing AI assistant request: {e}")
            return None

    async def handle_chat_request(self, request: AIAssistantRequest) -> str:
        """Обработка чат-запроса"""
        # Получаем историю чата для контекста
        chat_history = await self.get_chat_history(request.chat_id, limit=10)
        
        # Формируем промпт
        prompt = self.build_chat_prompt(request.message, chat_history)
        
        # Вызываем LLM
        response = await self.call_llm(
            model=request.context.get('model', config.CHAT_MODEL) if request.context else config.CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant in a messenger application."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response

    async def handle_summarization_request(self, request: AIAssistantRequest) -> str:
        """Обработка запроса на суммаризацию"""
        # Формируем промпт для суммаризации
        prompt = f"Please summarize the following text:\n\n{request.message}"
        
        # Вызываем LLM
        response = await self.call_llm(
            model=request.context.get('model', config.SUMMARIZATION_MODEL) if request.context else config.SUMMARIZATION_MODEL,
            messages=[
                {"role": "system", "content": "You are a text summarization assistant. Provide concise summaries."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response

    async def handle_translation_request(self, request: AIAssistantRequest) -> str:
        """Обработка запроса на перевод"""
        target_lang = request.options.get('target_language', 'English') if request.options else 'English'
        
        # Формируем промпт для перевода
        prompt = f"Translate the following text to {target_lang}:\n\n{request.message}"
        
        # Вызываем LLM
        response = await self.call_llm(
            model=request.context.get('model', config.TRANSLATION_MODEL) if request.context else config.TRANSLATION_MODEL,
            messages=[
                {"role": "system", "content": f"You are a translation assistant. Translate accurately to {target_lang}."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response

    async def handle_analysis_request(self, request: AIAssistantRequest) -> str:
        """Обработка запроса на анализ"""
        analysis_type = request.options.get('analysis_type', 'sentiment') if request.options else 'sentiment'
        
        if analysis_type == 'sentiment':
            prompt = f"Analyze the sentiment of the following text. Respond with POSITIVE, NEGATIVE, or NEUTRAL, and provide a brief explanation:\n\n{request.message}"
        elif analysis_type == 'keywords':
            prompt = f"Extract the main keywords from the following text:\n\n{request.message}"
        elif analysis_type == 'topics':
            prompt = f"Identify the main topics discussed in the following text:\n\n{request.message}"
        else:
            prompt = f"Analyze the following text and provide insights:\n\n{request.message}"
        
        # Вызываем LLM
        response = await self.call_llm(
            model=request.context.get('model', config.CHAT_MODEL) if request.context else config.CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are an analytical assistant. Provide detailed analysis."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response

    async def handle_scheduling_request(self, request: AIAssistantRequest) -> str:
        """Обработка запроса на планирование"""
        # Реализуем интеграцию с календарем
        try:
            # Извлекаем параметры из запроса
            event_title = request.params.get('title', 'Planned Event')
            event_description = request.params.get('description', 'Scheduled via AI Assistant')
            start_time = request.params.get('start_time')
            end_time = request.params.get('end_time')
            attendees = request.params.get('attendees', [])

            # Если время не указано, планируем на ближайшее удобное время
            if not start_time:
                from datetime import datetime, timedelta
                start_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            if not end_time:
                from datetime import datetime, timedelta
                end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()

            # Создаем событие в календаре пользователя
            calendar_event = {
                'title': event_title,
                'description': event_description,
                'start_time': start_time,
                'end_time': end_time,
                'attendees': attendees,
                'created_by_ai': True,
                'priority': request.params.get('priority', 'medium')
            }

            # Сохраняем событие в базу данных
            async with db_pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    INSERT INTO calendar_events (title, description, start_time, end_time, creator_id, attendees, created_at, priority)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                    """,
                    calendar_event['title'], calendar_event['description'], calendar_event['start_time'],
                    calendar_event['end_time'], request.user_id, calendar_event['attendees'],
                    datetime.utcnow(), calendar_event['priority']
                )

                event_id = result['id']

                # Отправляем уведомления участникам
                for attendee in calendar_event['attendees']:
                    await self._send_calendar_invitation(attendee, event_id, calendar_event)

            return f"Event '{calendar_event['title']}' scheduled successfully for {calendar_event['start_time']}. Event ID: {event_id}"

        except Exception as e:
            logger.error(f"Error handling scheduling request: {e}")
            return f"Error scheduling event: {str(e)}"

    async def handle_research_request(self, request: AIAssistantRequest) -> str:
        """Обработка запроса на исследование"""
        # В реальном приложении здесь будет интеграция с поисковыми API
        # Пока возвращаем заглушку
        return "Research functionality would search external sources and provide summaries."

    def build_chat_prompt(self, message: str, history: List[Dict]) -> str:
        """Построение промпта для чат-бота с историей"""
        prompt = "Previous conversation:\n"
        for msg in history:
            prompt += f"{msg['sender']}: {msg['content']}\n"
        prompt += f"\nNew message: {message}\n"
        prompt += "Please respond appropriately to the new message based on the conversation history."
        
        return prompt

    async def call_llm(self, model: str, messages: List[Dict], max_tokens: int = None) -> str:
        """Вызов LLM API"""
        if config.OPENAI_API_KEY:
            return await self.call_openai_api(model, messages, max_tokens)
        elif config.ANTHROPIC_API_KEY:
            return await self.call_anthropic_api(model, messages, max_tokens)
        elif config.HUGGINGFACE_API_KEY:
            return await self.call_huggingface_api(model, messages, max_tokens)
        else:
            # Возвращаем тестовый ответ, если нет API ключей
            return f"[AI Response to: {messages[-1]['content'][:50]}...]"

    async def call_openai_api(self, model: str, messages: List[Dict], max_tokens: int = None) -> str:
        """Вызов OpenAI API"""
        if not config.OPENAI_API_KEY:
            return "OpenAI API key not configured."
        
        headers = {
            'Authorization': f'Bearer {config.OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens or config.MAX_TOKENS
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)) as session:
                async with session.post('https://api.openai.com/v1/chat/completions', 
                                      headers=headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result['choices'][0]['message']['content'].strip()
                    else:
                        logger.error(f"OpenAI API error: {resp.status}, {await resp.text()}")
                        return "Error calling AI service."
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return "Error calling AI service."

    async def call_anthropic_api(self, model: str, messages: List[Dict], max_tokens: int = None) -> str:
        """Вызов Anthropic API (Claude)"""
        # В реальном приложении здесь будет реализация вызова Anthropic API
        return f"[Claude response to: {messages[-1]['content'][:50]}...]"

    async def call_huggingface_api(self, model: str, messages: List[Dict], max_tokens: int = None) -> str:
        """Вызов HuggingFace API"""
        # В реальном приложении здесь будет реализация вызова HuggingFace API
        return f"[HuggingFace response to: {messages[-1]['content'][:50]}...]"

    async def get_chat_history(self, chat_id: str, limit: int = 10) -> List[Dict]:
        """Получение истории чата для контекста"""
        # Получаем последние сообщения из базы данных
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT m.sender_id, u.username, m.content, m.timestamp
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.chat_id = $1
                ORDER BY m.timestamp DESC
                LIMIT $2
                ''',
                chat_id, limit
            )
        
        history = []
        for row in reversed(rows):  # Обратный порядок (новые внизу)
            history.append({
                'sender': row['username'],
                'content': row['content'],
                'timestamp': row['timestamp'].isoformat()
            })
        
        return history

    async def save_interaction(self, request: AIAssistantRequest, response: AIAssistantResponse):
        """Сохранение взаимодействия с ассистентом"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO ai_interactions (
                    assistant_id, user_id, chat_id, request_message, 
                    response_message, timestamp, latency
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ''',
                request.assistant_id, request.user_id, request.chat_id,
                request.message, response.response_message, 
                response.timestamp, response.latency
            )

    async def send_response_to_chat(self, response: AIAssistantResponse):
        """Отправка ответа ассистента в чат"""
        response_data = {
            'type': 'ai_assistant_response',
            'assistant_id': response.assistant_id,
            'response_message': response.response_message,
            'timestamp': response.timestamp.isoformat(),
            'latency': response.latency
        }
        
        await redis_client.publish(f"chat:{response.chat_id}", json.dumps(response_data))

    async def get_user_assistants(self, user_id: int) -> List[AIAssistant]:
        """Получение ассистентов пользователя"""
        assistants = []
        
        # Добавляем встроенные ассистенты
        for aid, assistant in self.assistants.items():
            if assistant.id.startswith('custom-'):
                # Это пользовательский ассистент, проверяем владельца
                async with db_pool.acquire() as conn:
                    owner = await conn.fetchval(
                        '''
                        SELECT owner_id FROM ai_assistants WHERE id = $1
                        ''',
                        assistant.id
                    )
                    if owner == user_id:
                        assistants.append(assistant)
            else:
                # Это встроенный ассистент
                assistants.append(assistant)
        
        return assistants

# Глобальный экземпляр сервиса
ai_assistant_service = AIAssistantService()

# Обработчики API
async def process_ai_request_handler(request):
    """Обработчик запроса к AI ассистенту"""
    data = await request.json()
    
    try:
        ai_request = AIAssistantRequest(**data)
        response = await ai_assistant_service.process_request(ai_request)
        
        if response:
            return web.json_response(response.dict())
        else:
            return web.json_response({'error': 'Failed to process request'}, status=500)
    except Exception as e:
        logger.error(f"Error processing AI request: {e}")
        return web.json_response({'error': 'Invalid request format'}, status=400)

async def create_custom_assistant_handler(request):
    """Обработчик создания пользовательского ассистента"""
    data = await request.json()
    
    name = data.get('name')
    description = data.get('description')
    assistant_type = data.get('type')
    model = data.get('model')
    user_id = data.get('user_id')
    
    if not all([name, description, assistant_type, model, user_id]):
        return web.json_response({'error': 'Missing required fields'}, status=400)
    
    try:
        assistant_type_enum = AssistantType(assistant_type)
        assistant = await ai_assistant_service.create_custom_assistant(
            name, description, assistant_type_enum, model, user_id
        )
        
        if assistant:
            return web.json_response(assistant.dict())
        else:
            return web.json_response({'error': 'Failed to create assistant'}, status=500)
    except ValueError:
        return web.json_response({'error': 'Invalid assistant type'}, status=400)

async def get_user_assistants_handler(request):
    """Обработчик получения ассистентов пользователя"""
    user_id = int(request.match_info['user_id'])
    
    assistants = await ai_assistant_service.get_user_assistants(user_id)
    return web.json_response({'assistants': [a.dict() for a in assistants]})

async def health_check(request):
    """Проверка состояния сервиса"""
    return web.json_response({'status': 'healthy', 'service': 'ai-assistant'})

async def init_app():
    """Инициализация приложения"""
    app = web.Application()
    
    # Маршруты
    app.router.add_post('/process', process_ai_request_handler)
    app.router.add_post('/assistants', create_custom_assistant_handler)
    app.router.add_get('/users/{user_id}/assistants', get_user_assistants_handler)
    app.router.add_get('/health', health_check)
    
    return app

async def main():
    """Основная функция запуска"""
    global db_pool, redis_client
    
    # Инициализация базы данных
    db_pool = await asyncpg.create_pool(
        os.getenv('DB_URL', 'postgresql://messenger:password@db:5432/messenger'),
        min_size=5, max_size=20
    )
    
    # Инициализация Redis
    redis_client = redis.from_url(
        os.getenv('REDIS_URL', 'redis://redis:6379'),
        decode_responses=True
    )
    
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', 8005)
    await site.start()
    
    logger.info("AI Assistant Service запущен на порту 8005")
    
    # Бесконечный цикл
    await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())