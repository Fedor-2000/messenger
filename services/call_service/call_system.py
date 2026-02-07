# Voice and Video Calling System
# File: services/call_service/call_system.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import secrets
import hashlib
from dataclasses import dataclass
import aiofiles
from pathlib import Path

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel
import aiortc

# Классы для обработки аудио и видео
class AudioProcessor:
    def __init__(self):
        self.audio_settings = {
            'codec': 'opus',
            'bitrate': 48000,
            'channels': 2
        }

    async def setup_audio_processing(self, track):
        """Настройка обработки аудио-трека"""
        # В реальной системе здесь будет настройка аудио-обработки
        logging.info(f"Setting up audio processing for track: {track.id}")
        # Здесь может быть настройка кодека, битрейта и т.д.
        return True

class VideoProcessor:
    def __init__(self):
        self.video_settings = {
            'codec': 'vp8',
            'resolution': '720p',
            'framerate': 30
        }

    async def setup_video_processing(self, track):
        """Настройка обработки видео-трека"""
        # В реальной системе здесь будет настройка видео-обработки
        logging.info(f"Setting up video processing for track: {track.id}")
        # Здесь может быть настройка кодека, разрешения, частоты кадров и т.д.
        return True
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from aiortc.rtcrtpsender import RTCRtpSender

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class CallType(Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SCREEN_SHARE = "screen_share"
    GROUP_AUDIO = "group_audio"
    GROUP_VIDEO = "group_video"

class CallStatus(Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    CONNECTED = "connected"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"
    MISSED = "missed"
    DECLINED = "declined"
    BUSY = "busy"

class CallDirection(Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"

class CallQuality(Enum):
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"

class ContentVisibility(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    FRIENDS_ONLY = "friends_only"
    GROUP_MEMBERS = "group_members"
    SPECIFIC_USERS = "specific_users"

class ContentModerationStatus(Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    FLAGGED = "flagged"

class Call(BaseModel):
    id: str
    caller_id: int
    callee_ids: List[int]  # Для групповых звонков
    type: CallType
    direction: CallDirection
    status: CallStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration: Optional[timedelta] = None
    quality: Optional[CallQuality] = None
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    signaling_data: Optional[Dict] = None  # Данные для WebRTC сигнализации
    ice_servers: List[Dict] = []  # Список STUN/TURN серверов
    recording_enabled: bool = False
    transcription_enabled: bool = False
    metadata: Optional[Dict] = None
    created_at: datetime = None
    updated_at: datetime = None

class CallParticipant(BaseModel):
    id: str
    call_id: str
    user_id: int
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None
    is_muted: bool = False
    is_video_enabled: bool = False
    is_screen_sharing: bool = False
    connection_quality: Optional[CallQuality] = None
    created_at: datetime = None

class CallSignal(BaseModel):
    id: str
    call_id: str
    sender_id: int
    receiver_id: int
    type: str  # 'offer', 'answer', 'candidate', 'ice_restart', 'bye'
    data: Dict[str, Any]  # SDP или ICE кандидат
    created_at: datetime = None

class CallStats(BaseModel):
    id: str
    call_id: str
    participant_id: int
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    jitter: float = 0.0
    packet_loss: float = 0.0
    rtt: float = 0.0  # Round trip time
    audio_level: float = 0.0
    video_fps: Optional[int] = None
    video_resolution: Optional[str] = None
    timestamp: datetime = None

class WebRTCManager:
    """Менеджер WebRTC соединений"""
    
    def __init__(self):
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.call_participants: Dict[str, List[str]] = {}  # call_id -> [participant_id]
        self.ice_servers = [
            {
                'urls': 'stun:stun.l.google.com:19302'
            },
            # В реальной системе здесь будут TURN сервера
        ]

    async def create_peer_connection(self, call_id: str, user_id: int) -> RTCPeerConnection:
        """Создание WebRTC соединения"""
        pc = RTCPeerConnection()
        
        # Добавляем ICE сервера
        for server in self.ice_servers:
            pc.addIceServer(server['urls'])
        
        # Сохраняем соединение
        connection_id = f"{call_id}:{user_id}"
        self.connections[connection_id] = pc
        
        # Обработчики событий
        @pc.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():
            logger.info(f"ICE connection state changed for {connection_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                await self._handle_ice_failure(call_id, user_id)

        @pc.on("track")
        def on_track(track):
            logger.info(f"Track received: {track.kind} from {connection_id}")
            # Обработка полученного медиа-трека
            # В реальной системе здесь будет обработка полученного трека
            # Добавляем трек в список активных треков для соединения
            if connection_id not in active_tracks:
                active_tracks[connection_id] = []
            active_tracks[connection_id].append(track)

            # В зависимости от типа трека (аудио/видео) выполняем соответствующую обработку
            if track.kind == "audio":
                # Настройка обработки аудио-трека
                audio_processor = AudioProcessor()
                await audio_processor.setup_audio_processing(track)
            elif track.kind == "video":
                # Настройка обработки видео-трека
                video_processor = VideoProcessor()
                await video_processor.setup_video_processing(track)

        return pc

    async def _handle_ice_failure(self, call_id: str, user_id: int):
        """Обработка сбоя ICE соединения"""
        logger.warning(f"ICE failure for call {call_id}, user {user_id}")
        # В реальной системе здесь будет попытка восстановления соединения
        # или переключение на резервный маршрут

    async def add_ice_candidate(self, call_id: str, user_id: int, candidate: Dict[str, Any]):
        """Добавление ICE кандидата"""
        connection_id = f"{call_id}:{user_id}"
        pc = self.connections.get(connection_id)
        
        if not pc:
            logger.error(f"No peer connection found for {connection_id}")
            return False

        try:
            ice_candidate = RTCIceCandidate(
                candidate['candidate'],
                sdpMid=candidate.get('sdpMid'),
                sdpMLineIndex=candidate.get('sdpMLineIndex')
            )
            await pc.addIceCandidate(ice_candidate)
            return True
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {e}")
            return False

    async def close_connection(self, call_id: str, user_id: int):
        """Закрытие WebRTC соединения"""
        connection_id = f"{call_id}:{user_id}"
        pc = self.connections.get(connection_id)
        
        if pc:
            await pc.close()
            del self.connections[connection_id]

    def get_ice_servers(self) -> List[Dict]:
        """Получение списка ICE серверов"""
        return self.ice_servers

class CallService:
    def __init__(self):
        self.webrtc_manager = WebRTCManager()
        self.active_calls: Dict[str, Call] = {}
        self.call_participants: Dict[str, List[CallParticipant]] = {}
        self.user_call_sessions: Dict[int, str] = {}  # user_id -> call_id
        self.max_call_duration = timedelta(hours=24)  # Максимальная длительность звонка
        self.max_participants = 50  # Максимальное количество участников в групповом звонке

    async def initiate_call(self, caller_id: int, callee_ids: List[int],
                           call_type: CallType, chat_id: Optional[str] = None,
                           group_id: Optional[str] = None,
                           project_id: Optional[str] = None,
                           enable_recording: bool = False,
                           enable_transcription: bool = False,
                           metadata: Optional[Dict] = None) -> Optional[str]:
        """Инициация звонка"""
        call_id = str(uuid.uuid4())

        # Проверяем права на инициацию звонка
        if not await self._can_initiate_call(caller_id, callee_ids, chat_id, group_id, project_id):
            return None

        # Проверяем, не заняты ли участники
        for callee_id in callee_ids:
            if await self._is_user_in_call(callee_id):
                # Отправляем уведомление о занятости
                await self._notify_user_busy(caller_id, callee_id)
                return None

        call = Call(
            id=call_id,
            caller_id=caller_id,
            callee_ids=callee_ids,
            type=call_type,
            direction=CallDirection.OUTGOING,
            status=CallStatus.INITIATED,
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            recording_enabled=enable_recording,
            transcription_enabled=enable_transcription,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Создаем участников звонка
        participants = []
        # Добавляем инициатора
        caller_participant = CallParticipant(
            id=str(uuid.uuid4()),
            call_id=call_id,
            user_id=caller_id,
            joined_at=datetime.utcnow(),
            is_muted=False,
            is_video_enabled=call_type in [CallType.VIDEO, CallType.GROUP_VIDEO],
            is_screen_sharing=False,
            created_at=datetime.utcnow()
        )
        participants.append(caller_participant)

        # Добавляем получателей
        for callee_id in callee_ids:
            callee_participant = CallParticipant(
                id=str(uuid.uuid4()),
                call_id=call_id,
                user_id=callee_id,
                is_muted=False,
                is_video_enabled=call_type in [CallType.VIDEO, CallType.GROUP_VIDEO],
                is_screen_sharing=False,
                created_at=datetime.utcnow()
            )
            participants.append(callee_participant)

        # Сохраняем звонок в базу данных
        await self._save_call_to_db(call)

        # Сохраняем участников
        await self._save_call_participants(participants)

        # Добавляем в активные звонки
        self.active_calls[call_id] = call
        self.call_participants[call_id] = participants

        # Отмечаем пользователей как находящихся в звонке
        for user_id in [caller_id] + callee_ids:
            self.user_call_sessions[user_id] = call_id

        # Отправляем приглашения на звонок
        await self._send_call_invitations(call, participants)

        # Создаем запись активности
        await self._log_activity(call_id, caller_id, "initiated", {
            "callee_count": len(callee_ids),
            "call_type": call_type.value
        })

        return call_id

    async def _save_call_to_db(self, call: Call):
        """Сохранение звонка в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO calls (
                    id, caller_id, callee_ids, type, direction, status,
                    started_at, ended_at, duration, quality, chat_id, group_id,
                    project_id, signaling_data, ice_servers, recording_enabled,
                    transcription_enabled, metadata, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                         $13, $14, $15, $16, $17, $18, $19, $20)
                """,
                call.id, call.caller_id, call.callee_ids, call.type.value,
                call.direction.value, call.status.value, call.started_at,
                call.ended_at, call.duration.total_seconds() if call.duration else None,
                call.quality.value if call.quality else None, call.chat_id,
                call.group_id, call.project_id, json.dumps(call.signaling_data) if call.signaling_data else None,
                json.dumps(call.ice_servers), call.recording_enabled,
                call.transcription_enabled, json.dumps(call.metadata) if call.metadata else None,
                call.created_at, call.updated_at
            )

    async def _save_call_participants(self, participants: List[CallParticipant]):
        """Сохранение участников звонка"""
        async with db_pool.acquire() as conn:
            for participant in participants:
                await conn.execute(
                    """
                    INSERT INTO call_participants (
                        id, call_id, user_id, joined_at, left_at, is_muted,
                        is_video_enabled, is_screen_sharing, connection_quality, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    participant.id, participant.call_id, participant.user_id,
                    participant.joined_at, participant.left_at, participant.is_muted,
                    participant.is_video_enabled, participant.is_screen_sharing,
                    participant.connection_quality.value if participant.connection_quality else None,
                    participant.created_at
                )

    async def _send_call_invitations(self, call: Call, participants: List[CallParticipant]):
        """Отправка приглашений на звонок"""
        for participant in participants:
            if participant.user_id != call.caller_id:  # Не отправляем инициатору
                invitation = {
                    'type': 'call_invitation',
                    'call': {
                        'id': call.id,
                        'caller_id': call.caller_id,
                        'type': call.type.value,
                        'direction': call.direction.value,
                        'chat_id': call.chat_id,
                        'group_id': call.group_id,
                        'project_id': call.project_id
                    },
                    'timestamp': datetime.utcnow().isoformat()
                }

                await self._send_notification_to_user(participant.user_id, invitation)

    async def respond_to_call(self, call_id: str, user_id: int, 
                            response: str) -> bool:  # 'accept', 'decline', 'busy'
        """Ответ на приглашение в звонок"""
        call = await self.get_call(call_id)
        if not call:
            return False

        # Проверяем, является ли пользователь получателем звонка
        if user_id not in call.callee_ids:
            return False

        # Проверяем статус звонка
        if call.status not in [CallStatus.INITIATED, CallStatus.RINGING]:
            return False

        if response == 'accept':
            return await self._accept_call(call, user_id)
        elif response == 'decline':
            return await self._decline_call(call, user_id)
        elif response == 'busy':
            return await self._mark_user_busy(call, user_id)
        else:
            return False

    async def _accept_call(self, call: Call, user_id: int) -> bool:
        """Принятие звонка пользователем"""
        # Обновляем статус звонка, если это первый ответ
        if call.status == CallStatus.INITIATED:
            call.status = CallStatus.RINGING
        elif call.status == CallStatus.RINGING:
            # Проверяем, все ли получатели ответили
            accepted_callees = []
            for callee_id in call.callee_ids:
                if await self._has_user_responded(call.id, callee_id):
                    response = await self._get_user_response(call.id, callee_id)
                    if response == 'accept':
                        accepted_callees.append(callee_id)

            # Если все получатели приняли звонок или это не групповой звонок
            if (call.type not in [CallType.GROUP_AUDIO, CallType.GROUP_VIDEO] or 
                len(accepted_callees) == len(call.callee_ids)):
                call.status = CallStatus.CONNECTED
                call.started_at = datetime.utcnow()

        call.updated_at = datetime.utcnow()

        # Обновляем участника
        participant = await self._get_call_participant(call.id, user_id)
        if participant:
            participant.joined_at = datetime.utcnow()
            await self._update_participant_in_db(participant)

        # Обновляем в базе данных
        await self._update_call_in_db(call)

        # Обновляем в активных звонках
        self.active_calls[call.id] = call

        # Создаем WebRTC соединение для пользователя
        await self._create_webrtc_connection(call.id, user_id)

        # Уведомляем других участников
        await self._notify_call_accepted(call, user_id)

        # Создаем запись активности
        await self._log_activity(call.id, user_id, "accepted", {})

        return True

    async def _decline_call(self, call: Call, user_id: int) -> bool:
        """Отклонение звонка пользователем"""
        call.status = CallStatus.DECLINED
        call.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_call_in_db(call)

        # Обновляем в активных звонках
        if call.id in self.active_calls:
            del self.active_calls[call.id]

        # Уведомляем инициатора
        await self._notify_call_declined(call, user_id)

        # Удаляем из сессий пользователей
        for participant_id in [call.caller_id] + call.callee_ids:
            if participant_id in self.user_call_sessions:
                del self.user_call_sessions[participant_id]

        # Закрываем WebRTC соединения
        await self._close_webrtc_connections(call.id)

        # Создаем запись активности
        await self._log_activity(call.id, user_id, "declined", {})

        return True

    async def _mark_user_busy(self, call: Call, user_id: int) -> bool:
        """Отметка пользователя как занятого"""
        call.status = CallStatus.BUSY
        call.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_call_in_db(call)

        # Уведомляем инициатора
        await self._notify_user_busy(call.caller_id, user_id)

        # Создаем запись активности
        await self._log_activity(call.id, user_id, "marked_busy", {})

        return True

    async def start_call(self, call_id: str, user_id: int) -> bool:
        """Начало звонка (когда все участники подключились)"""
        call = await self.get_call(call_id)
        if not call or call.caller_id != user_id:
            return False

        # Проверяем, все ли участники подключились
        if not await self._all_participants_connected(call):
            return False

        call.status = CallStatus.IN_PROGRESS
        call.started_at = datetime.utcnow()
        call.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_call_in_db(call)

        # Обновляем в активных звонках
        self.active_calls[call.id] = call

        # Уведомляем всех участников о начале звонка
        await self._notify_call_started(call)

        # Создаем запись активности
        await self._log_activity(call.id, user_id, "started", {})

        return True

    async def end_call(self, call_id: str, user_id: int) -> bool:
        """Завершение звонка"""
        call = await self.get_call(call_id)
        if not call:
            return False

        # Проверяем права на завершение звонка
        if user_id != call.caller_id and user_id not in call.callee_ids:
            return False

        # Обновляем статус
        call.status = CallStatus.ENDED
        call.ended_at = datetime.utcnow()
        if call.started_at:
            call.duration = call.ended_at - call.started_at
        call.updated_at = datetime.utcnow()

        # Обновляем в базе данных
        await self._update_call_in_db(call)

        # Обновляем участников
        await self._update_participants_on_call_end(call)

        # Удаляем из активных звонков
        if call.id in self.active_calls:
            del self.active_calls[call.id]

        # Удаляем из сессий пользователей
        for participant_id in [call.caller_id] + call.callee_ids:
            if participant_id in self.user_call_sessions:
                del self.user_call_sessions[participant_id]

        # Закрываем WebRTC соединения
        await self._close_webrtc_connections(call.id)

        # Уведомляем участников о завершении звонка
        await self._notify_call_ended(call)

        # Создаем запись активности
        await self._log_activity(call.id, user_id, "ended", {
            "duration": call.duration.total_seconds() if call.duration else 0
        })

        return True

    async def _update_call_in_db(self, call: Call):
        """Обновление звонка в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE calls SET
                    status = $2, started_at = $3, ended_at = $4, duration = $5,
                    quality = $6, updated_at = $7
                WHERE id = $1
                """,
                call.id, call.status.value, call.started_at, call.ended_at,
                call.duration.total_seconds() if call.duration else None,
                call.quality.value if call.quality else None, call.updated_at
            )

    async def _update_participants_on_call_end(self, call: Call):
        """Обновление участников при завершении звонка"""
        async with db_pool.acquire() as conn:
            # Отмечаем всех участников как покинувших звонок
            await conn.execute(
                """
                UPDATE call_participants SET
                    left_at = $2
                WHERE call_id = $1 AND left_at IS NULL
                """,
                call.id, call.ended_at
            )

    async def _create_webrtc_connection(self, call_id: str, user_id: int):
        """Создание WebRTC соединения для пользователя"""
        try:
            pc = await self.webrtc_manager.create_peer_connection(call_id, user_id)
            
            # В реальной системе здесь будет создание локальных описаний и обмен сигналами
            # Для упрощения просто создаем соединение
            
            # Если это групповой звонок, подключаем к другим участникам
            if call_id in self.call_participants:
                participants = self.call_participants[call_id]
                for participant in participants:
                    if participant.user_id != user_id:
                        # В реальной системе здесь будет установка соединения с другими участниками
                        import logging
                        logging.info(f"Setting up WebRTC connection between {user_id} and {participant.user_id}")
                        
        except Exception as e:
            logger.error(f"Error creating WebRTC connection for user {user_id}: {e}")

    async def _close_webrtc_connections(self, call_id: str):
        """Закрытие всех WebRTC соединений для звонка"""
        # Получаем всех участников звонка
        async with db_pool.acquire() as conn:
            participant_rows = await conn.fetch(
                "SELECT user_id FROM call_participants WHERE call_id = $1",
                call_id
            )

        for row in participant_rows:
            user_id = row['user_id']
            await self.webrtc_manager.close_connection(call_id, user_id)

    async def send_call_signal(self, call_id: str, sender_id: int, 
                             receiver_id: int, signal_type: str, 
                             signal_data: Dict[str, Any]) -> bool:
        """Отправка сигнала для WebRTC соединения"""
        call = await self.get_call(call_id)
        if not call:
            return False

        # Проверяем, являются ли отправитель и получатель участниками звонка
        all_participants = [call.caller_id] + call.callee_ids
        if sender_id not in all_participants or receiver_id not in all_participants:
            return False

        signal = CallSignal(
            id=str(uuid.uuid4()),
            call_id=call_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            type=signal_type,
            data=signal_data,
            created_at=datetime.utcnow()
        )

        # Сохраняем сигнал в базу данных
        await self._save_call_signal(signal)

        # Отправляем сигнал получателю
        await self._send_signal_to_user(receiver_id, signal)

        # Если это ICE кандидат, добавляем к WebRTC соединению
        if signal_type == 'candidate':
            await self.webrtc_manager.add_ice_candidate(call_id, receiver_id, signal_data)

        return True

    async def _save_call_signal(self, signal: CallSignal):
        """Сохранение сигнала в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO call_signals (
                    id, call_id, sender_id, receiver_id, type, data, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                signal.id, signal.call_id, signal.sender_id, signal.receiver_id,
                signal.type, json.dumps(signal.data), signal.created_at
            )

    async def _send_signal_to_user(self, user_id: int, signal: CallSignal):
        """Отправка сигнала пользователю"""
        notification = {
            'type': 'call_signal',
            'signal': {
                'id': signal.id,
                'call_id': signal.call_id,
                'sender_id': signal.sender_id,
                'type': signal.type,
                'data': signal.data
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(user_id, notification)

    async def get_user_active_calls(self, user_id: int) -> List[Call]:
        """Получение активных звонков пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id, c.caller_id, c.callee_ids, c.type, c.direction, c.status,
                       c.started_at, c.ended_at, c.duration, c.quality, c.chat_id,
                       c.group_id, c.project_id, c.signaling_data, c.ice_servers,
                       c.recording_enabled, c.transcription_enabled, c.metadata,
                       c.created_at, c.updated_at
                FROM calls c
                JOIN call_participants cp ON c.id = cp.call_id
                WHERE cp.user_id = $1 AND c.status IN ('initiated', 'ringing', 'connected', 'in_progress')
                ORDER BY c.created_at DESC
                """,
                user_id
            )

        calls = []
        for row in rows:
            call = Call(
                id=row['id'],
                caller_id=row['caller_id'],
                callee_ids=row['callee_ids'] or [],
                type=CallType(row['type']),
                direction=CallDirection(row['direction']),
                status=CallStatus(row['status']),
                started_at=row['started_at'],
                ended_at=row['ended_at'],
                duration=timedelta(seconds=row['duration']) if row['duration'] else None,
                quality=CallQuality(row['quality']) if row['quality'] else None,
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                signaling_data=json.loads(row['signaling_data']) if row['signaling_data'] else None,
                ice_servers=json.loads(row['ice_servers']) if row['ice_servers'] else [],
                recording_enabled=row['recording_enabled'],
                transcription_enabled=row['transcription_enabled'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            calls.append(call)

        return calls

    async def get_call_history(self, user_id: int, limit: int = 50, 
                             offset: int = 0) -> List[Call]:
        """Получение истории звонков пользователя"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.id, c.caller_id, c.callee_ids, c.type, c.direction, c.status,
                       c.started_at, c.ended_at, c.duration, c.quality, c.chat_id,
                       c.group_id, c.project_id, c.signaling_data, c.ice_servers,
                       c.recording_enabled, c.transcription_enabled, c.metadata,
                       c.created_at, c.updated_at
                FROM calls c
                JOIN call_participants cp ON c.id = cp.call_id
                WHERE cp.user_id = $1 AND c.status IN ('ended', 'missed', 'declined', 'busy')
                ORDER BY c.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id, limit, offset
            )

        calls = []
        for row in rows:
            call = Call(
                id=row['id'],
                caller_id=row['caller_id'],
                callee_ids=row['callee_ids'] or [],
                type=CallType(row['type']),
                direction=CallDirection(row['direction']),
                status=CallStatus(row['status']),
                started_at=row['started_at'],
                ended_at=row['ended_at'],
                duration=timedelta(seconds=row['duration']) if row['duration'] else None,
                quality=CallQuality(row['quality']) if row['quality'] else None,
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                signaling_data=json.loads(row['signaling_data']) if row['signaling_data'] else None,
                ice_servers=json.loads(row['ice_servers']) if row['ice_servers'] else [],
                recording_enabled=row['recording_enabled'],
                transcription_enabled=row['transcription_enabled'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            calls.append(call)

        return calls

    async def _can_initiate_call(self, caller_id: int, callee_ids: List[int],
                               chat_id: Optional[str], group_id: Optional[str],
                               project_id: Optional[str]) -> bool:
        """Проверка прав на инициацию звонка"""
        # Проверяем, не находится ли инициатор в другом звонке
        if await self._is_user_in_call(caller_id):
            return False

        # Проверяем, не находятся ли получатели в других звонках
        for callee_id in callee_ids:
            if await self._is_user_in_call(callee_id):
                return False

        # Проверяем права доступа к чату/группе/проекту
        if chat_id:
            return await self._can_access_chat(chat_id, caller_id)
        elif group_id:
            return await self._is_group_member(caller_id, group_id)
        elif project_id:
            return await self._is_project_member(caller_id, project_id)
        else:
            # Проверяем, являются ли пользователи друзьями
            for callee_id in callee_ids:
                if not await self._are_friends(caller_id, callee_id):
                    return False

        return True

    async def _is_user_in_call(self, user_id: int) -> bool:
        """Проверка, находится ли пользователь в звонке"""
        return user_id in self.user_call_sessions

    async def _all_participants_connected(self, call: Call) -> bool:
        """Проверка, все ли участники подключились к звонку"""
        async with db_pool.acquire() as conn:
            connected_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM call_participants
                WHERE call_id = $1 AND joined_at IS NOT NULL AND left_at IS NULL
                """,
                call.id
            )

        expected_count = len([call.caller_id] + call.callee_ids)
        return connected_count == expected_count

    async def _has_user_responded(self, call_id: str, user_id: int) -> bool:
        """Проверка, ответил ли пользователь на звонок"""
        # В реальной системе здесь будет проверка отдельной таблицы ответов
        # или более сложная логика
        # Для упрощения проверим, есть ли участник с этим ID
        participant = await self._get_call_participant(call_id, user_id)
        return participant is not None

    async def _get_user_response(self, call_id: str, user_id: int) -> Optional[str]:
        """Получение ответа пользователя на звонок"""
        # В реальной системе здесь будет получение из таблицы ответов
        # или проверка статуса участника
        participant = await self._get_call_participant(call_id, user_id)
        if participant and participant.joined_at:
            return 'accept'
        return None

    async def _get_call_participant(self, call_id: str, user_id: int) -> Optional[CallParticipant]:
        """Получение участника звонка"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, call_id, user_id, joined_at, left_at, is_muted,
                       is_video_enabled, is_screen_sharing, connection_quality, created_at
                FROM call_participants
                WHERE call_id = $1 AND user_id = $2
                """,
                call_id, user_id
            )

        if not row:
            return None

        return CallParticipant(
            id=row['id'],
            call_id=row['call_id'],
            user_id=row['user_id'],
            joined_at=row['joined_at'],
            left_at=row['left_at'],
            is_muted=row['is_muted'],
            is_video_enabled=row['is_video_enabled'],
            is_screen_sharing=row['is_screen_sharing'],
            connection_quality=CallQuality(row['connection_quality']) if row['connection_quality'] else None,
            created_at=row['created_at']
        )

    async def _update_participant_in_db(self, participant: CallParticipant):
        """Обновление участника в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE call_participants SET
                    joined_at = $2, left_at = $3, is_muted = $4,
                    is_video_enabled = $5, is_screen_sharing = $6,
                    connection_quality = $7, updated_at = $8
                WHERE id = $1
                """,
                participant.id, participant.joined_at, participant.left_at,
                participant.is_muted, participant.is_video_enabled,
                participant.is_screen_sharing,
                participant.connection_quality.value if participant.connection_quality else None,
                datetime.utcnow()
            )

    async def _notify_call_accepted(self, call: Call, user_id: int):
        """Уведомление об принятии звонка"""
        notification = {
            'type': 'call_accepted',
            'call_id': call.id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам звонка
        all_participants = [call.caller_id] + call.callee_ids
        for participant_id in all_participants:
            if participant_id != user_id:  # Не отправляем самому принявшему
                await self._send_notification_to_user(participant_id, notification)

    async def _notify_call_declined(self, call: Call, user_id: int):
        """Уведомление об отклонении звонка"""
        notification = {
            'type': 'call_declined',
            'call_id': call.id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем инициатору звонка
        await self._send_notification_to_user(call.caller_id, notification)

    async def _notify_user_busy(self, caller_id: int, busy_user_id: int):
        """Уведомление о занятости пользователя"""
        notification = {
            'type': 'user_busy',
            'user_id': busy_user_id,
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(caller_id, notification)

    async def _notify_call_started(self, call: Call):
        """Уведомление о начале звонка"""
        notification = {
            'type': 'call_started',
            'call': {
                'id': call.id,
                'type': call.type.value,
                'chat_id': call.chat_id,
                'group_id': call.group_id,
                'project_id': call.project_id
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам звонка
        all_participants = [call.caller_id] + call.callee_ids
        for participant_id in all_participants:
            await self._send_notification_to_user(participant_id, notification)

    async def _notify_call_ended(self, call: Call):
        """Уведомление о завершении звонка"""
        notification = {
            'type': 'call_ended',
            'call_id': call.id,
            'duration': call.duration.total_seconds() if call.duration else 0,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам звонка
        all_participants = [call.caller_id] + call.callee_ids
        for participant_id in all_participants:
            await self._send_notification_to_user(participant_id, notification)

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:calls"
        await redis_client.publish(channel, json.dumps(notification))

    async def _log_activity(self, call_id: str, user_id: int, action: str, details: Dict[str, Any]):
        """Логирование активности по звонку"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'call_id': call_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush(f"call_activities:{call_id}", json.dumps(activity))
        await redis_client.ltrim(f"call_activities:{call_id}", 0, 99)  # Храним последние 100 активностей

    async def _can_access_chat(self, chat_id: str, user_id: int) -> bool:
        """Проверка прав доступа к чату"""
        # В реальной системе здесь будет проверка участия в чате
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    async def _is_project_member(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь участником проекта"""
        # В реальной системе здесь будет проверка в таблице участников проекта
        return False

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def get_call(self, call_id: str) -> Optional[Call]:
        """Получение звонка по ID"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, caller_id, callee_ids, type, direction, status,
                       started_at, ended_at, duration, quality, chat_id,
                       group_id, project_id, signaling_data, ice_servers,
                       recording_enabled, transcription_enabled, metadata,
                       created_at, updated_at
                FROM calls WHERE id = $1
                """,
                call_id
            )

        if not row:
            return None

        return Call(
            id=row['id'],
            caller_id=row['caller_id'],
            callee_ids=row['callee_ids'] or [],
            type=CallType(row['type']),
            direction=CallDirection(row['direction']),
            status=CallStatus(row['status']),
            started_at=row['started_at'],
            ended_at=row['ended_at'],
            duration=timedelta(seconds=row['duration']) if row['duration'] else None,
            quality=CallQuality(row['quality']) if row['quality'] else None,
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            signaling_data=json.loads(row['signaling_data']) if row['signaling_data'] else None,
            ice_servers=json.loads(row['ice_servers']) if row['ice_servers'] else [],
            recording_enabled=row['recording_enabled'],
            transcription_enabled=row['transcription_enabled'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

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
call_service = CallService()