"""
WebRTC Signaling Manager
File: server/app/webrtc/signaling.py
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

import aiohttp
from aiohttp import web, WSMsgType
import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class CallStatus(Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    ENDED = "ended"
    MISSED = "missed"

class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN_SHARE = "screen_share"

class WebRTCSession(BaseModel):
    session_id: str
    caller_id: int
    callee_id: int
    media_types: List[MediaType]
    status: CallStatus = CallStatus.INITIATED
    initiated_at: datetime = None
    accepted_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration: Optional[int] = None  # in seconds
    participants: List[int] = None  # IDs of participants
    signaling_data: Dict[str, Any] = None  # SDP offer/answer, ICE candidates

class WebRTCSignalingManager:
    """Менеджер WebRTC сигнализации"""
    
    def __init__(self):
        self.active_sessions: Dict[str, WebRTCSession] = {}
        self.pending_calls: Dict[str, WebRTCSession] = {}  # caller_id -> session
        self.call_participants: Dict[str, List[int]] = {}  # session_id -> [user_ids]
        self.websocket_connections: Dict[int, web.WebSocketResponse] = {}  # user_id -> ws
        self.db_pool = None
        self.redis = None
        
    async def initialize(self, db_pool_param, redis_param):
        """Инициализация менеджера сигнализации"""
        self.db_pool = db_pool_param
        self.redis = redis_param
        
        # Загружаем активные сессии из базы данных
        await self._load_active_sessions()
        
        logger.info("WebRTC signaling manager initialized")
    
    async def _load_active_sessions(self):
        """Загрузка активных сессий из базы данных"""
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT session_id, caller_id, callee_id, media_types, status, 
                           initiated_at, accepted_at, ended_at, duration
                    FROM call_sessions 
                    WHERE status IN ('initiated', 'ringing', 'accepted')
                    """
                )
                
                for row in rows:
                    session = WebRTCSession(
                        session_id=row['session_id'],
                        caller_id=row['caller_id'],
                        callee_id=row['callee_id'],
                        media_types=[MediaType(mt) for mt in row['media_types']],
                        status=CallStatus(row['status']),
                        initiated_at=row['initiated_at'],
                        accepted_at=row['accepted_at'],
                        ended_at=row['ended_at'],
                        duration=row['duration']
                    )
                    self.active_sessions[session.session_id] = session
                    
        except Exception as e:
            logger.error(f"Error loading active WebRTC sessions: {e}")
    
    async def initiate_call(self, caller_id: int, callee_id: int, 
                           media_types: List[MediaType]) -> Optional[str]:
        """Инициация звонка"""
        session_id = str(uuid.uuid4())
        
        # Проверяем, не занят ли уже пользователь в другом звонке
        if await self._is_user_in_call(callee_id):
            logger.warning(f"User {callee_id} is already in a call")
            return None
        
        # Создаем сессию
        session = WebRTCSession(
            session_id=session_id,
            caller_id=caller_id,
            callee_id=callee_id,
            media_types=media_types,
            status=CallStatus.INITIATED,
            initiated_at=datetime.utcnow()
        )
        
        # Сохраняем в базу данных
        await self._save_call_session(session)
        
        # Добавляем в активные сессии
        self.active_sessions[session_id] = session
        self.pending_calls[f"{caller_id}_{callee_id}"] = session
        
        # Отправляем приглашение получателю
        await self._send_call_invitation(callee_id, session)
        
        logger.info(f"Call initiated from {caller_id} to {callee_id}, session: {session_id}")
        
        return session_id
    
    async def accept_call(self, session_id: str, user_id: int) -> bool:
        """Принятие звонка"""
        if session_id not in self.active_sessions:
            logger.warning(f"Call session {session_id} not found")
            return False
            
        session = self.active_sessions[session_id]
        
        # Проверяем, что пользователь - получатель звонка
        if session.callee_id != user_id:
            logger.warning(f"User {user_id} is not the callee for session {session_id}")
            return False
            
        # Обновляем статус
        session.status = CallStatus.ACCEPTED
        session.accepted_at = datetime.utcnow()
        
        # Обновляем в базе данных
        await self._update_call_session(session)
        
        # Удаляем из ожидающих
        call_key = f"{session.caller_id}_{session.callee_id}"
        if call_key in self.pending_calls:
            del self.pending_calls[call_key]
        
        # Отправляем подтверждение инициатору
        await self._send_call_acceptance(session.caller_id, session)
        
        logger.info(f"Call {session_id} accepted by {user_id}")
        
        return True
    
    async def decline_call(self, session_id: str, user_id: int) -> bool:
        """Отклонение звонка"""
        if session_id not in self.active_sessions:
            logger.warning(f"Call session {session_id} not found")
            return False
            
        session = self.active_sessions[session_id]
        
        # Проверяем, что пользователь - получатель звонка
        if session.callee_id != user_id:
            logger.warning(f"User {user_id} is not the callee for session {session_id}")
            return False
            
        # Обновляем статус
        session.status = CallStatus.DECLINED
        session.ended_at = datetime.utcnow()
        
        # Обновляем в базе данных
        await self._update_call_session(session)
        
        # Удаляем из активных сессий
        del self.active_sessions[session_id]
        
        # Удаляем из ожидающих
        call_key = f"{session.caller_id}_{session.callee_id}"
        if call_key in self.pending_calls:
            del self.pending_calls[call_key]
        
        # Отправляем подтверждение инициатору
        await self._send_call_decline(session.caller_id, session)
        
        logger.info(f"Call {session_id} declined by {user_id}")
        
        return True
    
    async def end_call(self, session_id: str, user_id: int) -> bool:
        """Завершение звонка"""
        if session_id not in self.active_sessions:
            logger.warning(f"Call session {session_id} not found")
            return False
            
        session = self.active_sessions[session_id]
        
        # Проверяем, что пользователь участвует в звонке
        if session.caller_id != user_id and session.callee_id != user_id:
            logger.warning(f"User {user_id} is not participant in session {session_id}")
            return False
            
        # Обновляем статус
        session.status = CallStatus.ENDED
        session.ended_at = datetime.utcnow()
        
        # Вычисляем продолжительность
        if session.accepted_at:
            duration = (session.ended_at - session.accepted_at).total_seconds()
            session.duration = int(duration)
        
        # Обновляем в базе данных
        await self._update_call_session(session)
        
        # Удаляем из активных сессий
        del self.active_sessions[session_id]
        
        # Удаляем из ожидающих
        call_key = f"{session.caller_id}_{session.callee_id}"
        if call_key in self.pending_calls:
            del self.pending_calls[call_key]
        
        # Отправляем уведомление обоим участникам
        await self._send_call_ended(session.caller_id, session)
        await self._send_call_ended(session.callee_id, session)
        
        logger.info(f"Call {session_id} ended by {user_id}")
        
        return True
    
    async def _is_user_in_call(self, user_id: int) -> bool:
        """Проверка, находится ли пользователь в звонке"""
        for session in self.active_sessions.values():
            if session.status in [CallStatus.RINGING, CallStatus.ACCEPTED] and \
               (session.caller_id == user_id or session.callee_id == user_id):
                return True
        return False
    
    async def _save_call_session(self, session: WebRTCSession):
        """Сохранение сессии звонка в базу данных"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO call_sessions (
                        session_id, caller_id, callee_id, media_types, status,
                        initiated_at, accepted_at, ended_at, duration
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (session_id) DO UPDATE SET
                        status = $5, accepted_at = $7, ended_at = $8, duration = $9
                    """,
                    session.session_id, session.caller_id, session.callee_id,
                    [mt.value for mt in session.media_types], session.status.value,
                    session.initiated_at, session.accepted_at, session.ended_at, session.duration
                )
        except Exception as e:
            logger.error(f"Error saving call session {session.session_id}: {e}")
    
    async def _update_call_session(self, session: WebRTCSession):
        """Обновление сессии звонка в базе данных"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE call_sessions SET
                        status = $2, accepted_at = $3, ended_at = $4, duration = $5
                    WHERE session_id = $1
                    """,
                    session.session_id, session.status.value, session.accepted_at,
                    session.ended_at, session.duration
                )
        except Exception as e:
            logger.error(f"Error updating call session {session.session_id}: {e}")
    
    async def _send_call_invitation(self, callee_id: int, session: WebRTCSession):
        """Отправка приглашения на звонок"""
        invitation_data = {
            'type': 'call_invitation',
            'session_id': session.session_id,
            'caller_id': session.caller_id,
            'media_types': [mt.value for mt in session.media_types],
            'timestamp': session.initiated_at.isoformat()
        }
        
        # Отправляем через WebSocket
        await self._send_to_user(callee_id, invitation_data)
    
    async def _send_call_acceptance(self, user_id: int, session: WebRTCSession):
        """Отправка подтверждения принятия звонка"""
        acceptance_data = {
            'type': 'call_accepted',
            'session_id': session.session_id,
            'callee_id': session.callee_id,
            'timestamp': session.accepted_at.isoformat()
        }
        
        # Отправляем через WebSocket
        await self._send_to_user(user_id, acceptance_data)
    
    async def _send_call_decline(self, user_id: int, session: WebRTCSession):
        """Отправка подтверждения отклонения звонка"""
        decline_data = {
            'type': 'call_declined',
            'session_id': session.session_id,
            'callee_id': session.callee_id,
            'timestamp': session.ended_at.isoformat()
        }
        
        # Отправляем через WebSocket
        await self._send_to_user(user_id, decline_data)
    
    async def _send_call_ended(self, user_id: int, session: WebRTCSession):
        """Отправка уведомления о завершении звонка"""
        end_data = {
            'type': 'call_ended',
            'session_id': session.session_id,
            'duration': session.duration,
            'timestamp': session.ended_at.isoformat()
        }
        
        # Отправляем через WebSocket
        await self._send_to_user(user_id, end_data)
    
    async def _send_to_user(self, user_id: int, data: Dict[str, Any]):
        """Отправка данных пользователю через WebSocket или Redis"""
        # Сначала пробуем через WebSocket
        if user_id in self.websocket_connections:
            try:
                ws = self.websocket_connections[user_id]
                await ws.send_str(json.dumps(data))
            except Exception as e:
                logger.error(f"Error sending to WebSocket for user {user_id}: {e}")
                # Если не удалось через WebSocket, отправляем через Redis
                await self._send_via_redis(user_id, data)
        else:
            # Отправляем через Redis
            await self._send_via_redis(user_id, data)
    
    async def _send_via_redis(self, user_id: int, data: Dict[str, Any]):
        """Отправка данных пользователю через Redis"""
        try:
            channel = f"user:{user_id}:webrtc"
            await self.redis.publish(channel, json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending via Redis to user {user_id}: {e}")
    
    async def handle_signaling_message(self, user_id: int, message: Dict[str, Any]):
        """Обработка сигнального сообщения WebRTC"""
        session_id = message.get('session_id')
        message_type = message.get('type')
        
        if not session_id:
            logger.warning(f"No session_id in signaling message from user {user_id}")
            return False
        
        if session_id not in self.active_sessions:
            logger.warning(f"Signaling message for non-existent session {session_id}")
            return False
        
        session = self.active_sessions[session_id]
        
        # Проверяем, что пользователь является участником сессии
        if user_id != session.caller_id and user_id != session.callee_id:
            logger.warning(f"User {user_id} is not participant in session {session_id}")
            return False
        
        # Обработка различных типов сигнальных сообщений
        if message_type == 'offer':
            # SDP offer от инициатора к получателю
            target_user = session.callee_id if user_id == session.caller_id else session.caller_id
            await self._relay_signaling_data(target_user, message)
        elif message_type == 'answer':
            # SDP answer от получателя к инициатору
            target_user = session.callee_id if user_id == session.caller_id else session.caller_id
            await self._relay_signaling_data(target_user, message)
        elif message_type == 'ice_candidate':
            # ICE candidate от одного участника другому
            target_user = session.callee_id if user_id == session.caller_id else session.caller_id
            await self._relay_signaling_data(target_user, message)
        elif message_type == 'hangup':
            # Завершение звонка
            await self.end_call(session_id, user_id)
        else:
            logger.warning(f"Unknown signaling message type: {message_type}")
            return False
        
        return True
    
    async def _relay_signaling_data(self, target_user_id: int, data: Dict[str, Any]):
        """Ретрансляция сигнальных данных другому участнику"""
        await self._send_to_user(target_user_id, data)

# Глобальный экземпляр для использования в приложении
webrtc_signaling_manager = WebRTCSignalingManager()