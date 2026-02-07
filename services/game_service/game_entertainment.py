# Game and Entertainment System
# File: services/game_service/game_entertainment.py

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import random
import hashlib
from abc import ABC, abstractmethod

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Глобальные переменные
db_pool = None
redis_client = None

class GameType(Enum):
    TRIVIA = "trivia"
    WORD_GAMES = "word_games"
    BOARD_GAMES = "board_games"
    CARD_GAMES = "card_games"
    PUZZLES = "puzzles"
    QUIZZES = "quizzes"
    MINI_GAMES = "mini_games"
    MULTIPLAYER_GAMES = "multiplayer_games"
    CASUAL_GAMES = "casual_games"
    STRATEGY_GAMES = "strategy_games"
    ARCADE_GAMES = "arcade_games"

class GameStatus(Enum):
    LOBBY = "lobby"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"

class GamePrivacy(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    FRIENDS_ONLY = "friends_only"
    INVITE_ONLY = "invite_only"

class GameDifficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"

class GameMode(Enum):
    SINGLE_PLAYER = "single_player"
    MULTIPLAYER = "multiplayer"
    COMPETITIVE = "competitive"
    COOPERATIVE = "cooperative"
    TOURNAMENT = "tournament"

class GameCategory(Enum):
    EDUCATIONAL = "educational"
    ENTERTAINMENT = "entertainment"
    BRAIN_TRAINING = "brain_training"
    SOCIAL = "social"
    COMPETITIVE = "competitive"

class Game(BaseModel):
    id: str
    title: str
    description: str
    type: GameType
    category: GameCategory
    creator_id: int
    privacy: GamePrivacy
    status: GameStatus
    mode: GameMode
    difficulty: GameDifficulty
    max_players: int
    min_players: int
    current_players: List[int] = []
    spectators: List[int] = []  # ID наблюдателей
    settings: Dict[str, Any] = {}  # Настройки игры
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration: Optional[timedelta] = None  # Ожидаемое время игры
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    project_id: Optional[str] = None
    is_recurring: bool = False  # Для регулярных игровых сессий
    recurrence_pattern: Optional[str] = None  # Для регулярных игр
    next_occurrence: Optional[datetime] = None  # Следующее occurrence для регулярных игр
    metadata: Optional[Dict] = None
    created_at: datetime = None
    updated_at: datetime = None

class GameSession(BaseModel):
    id: str
    game_id: str
    players: List[Dict[str, Any]]  # [{'user_id': id, 'score': 0, 'status': 'active'}]
    current_round: int = 1
    total_rounds: int = 1
    started_at: datetime = None
    ended_at: Optional[datetime] = None
    game_state: Dict[str, Any] = {}  # Состояние игры
    scores: Dict[int, int] = {}  # {user_id: score}
    leaderboards: List[Dict[str, Any]] = []  # [{'user_id': id, 'score': score, 'rank': 1}]
    chat_id: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

class GameMove(BaseModel):
    id: str
    game_session_id: str
    player_id: int
    move_type: str  # 'play_card', 'place_piece', 'answer', etc.
    move_data: Dict[str, Any]  # Данные хода
    timestamp: datetime = None

class GameInvite(BaseModel):
    id: str
    game_id: str
    inviter_id: int
    invitee_id: int
    status: str  # 'pending', 'accepted', 'declined', 'expired'
    created_at: datetime = None
    expires_at: Optional[datetime] = None

class GameAchievement(BaseModel):
    id: str
    user_id: int
    achievement_type: str  # 'first_win', 'win_streak', 'perfect_score', etc.
    name: str
    description: str
    points: int
    unlocked_at: datetime = None
    metadata: Optional[Dict] = None

class GameLeaderboardEntry(BaseModel):
    user_id: int
    username: str
    score: int
    rank: int
    games_played: int
    games_won: int
    win_rate: float
    last_played: datetime

class GameService:
    def __init__(self):
        self.active_games: Dict[str, GameSession] = {}
        self.game_factories = {}
        self.achievements_registry = {}
        self.max_players_per_game = 100  # Максимальное количество игроков в одной игре
        self.game_timeout = timedelta(minutes=30)  # Таймаут для неактивных игр
        self.register_default_games()

    def register_game_factory(self, game_type: GameType, factory_func):
        """Регистрация фабрики для создания игр определенного типа"""
        self.game_factories[game_type] = factory_func

    def register_achievement(self, achievement_type: str, name: str, description: str, points: int):
        """Регистрация достижения"""
        self.achievements_registry[achievement_type] = {
            'name': name,
            'description': description,
            'points': points
        }

    def register_default_games(self):
        """Регистрация стандартных игр"""
        self.register_game_factory(GameType.TRIVIA, TriviaGameFactory)
        self.register_game_factory(GameType.WORD_GAMES, WordGameFactory)
        self.register_game_factory(GameType.BOARD_GAMES, BoardGameFactory)
        self.register_game_factory(GameType.CARD_GAMES, CardGameFactory)
        self.register_game_factory(GameType.PUZZLES, PuzzleGameFactory)
        self.register_game_factory(GameType.QUIZZES, QuizGameFactory)
        self.register_game_factory(GameType.MINI_GAMES, MiniGameFactory)
        self.register_game_factory(GameType.MULTIPLAYER_GAMES, MultiplayerGameFactory)
        self.register_game_factory(GameType.CASUAL_GAMES, CasualGameFactory)
        self.register_game_factory(GameType.STRATEGY_GAMES, StrategyGameFactory)
        self.register_game_factory(GameType.ARCADE_GAMES, ArcadeGameFactory)

        # Регистрация стандартных достижений
        self.register_achievement('first_game', 'First Steps', 'Played your first game', 10)
        self.register_achievement('first_win', 'Victory!', 'Won your first game', 25)
        self.register_achievement('win_streak_3', 'Win Streak', 'Won 3 games in a row', 50)
        self.register_achievement('quiz_master', 'Quiz Master', 'Answered 10 quiz questions correctly', 30)
        self.register_achievement('speed_demon', 'Speed Demon', 'Completed a puzzle in record time', 40)
        self.register_achievement('social_gamer', 'Social Gamer', 'Played games with 10 different people', 35)
        self.register_achievement('champion', 'Champion', 'Reached #1 in leaderboard', 100)

    async def create_game(self, title: str, description: str, game_type: GameType,
                         creator_id: int, privacy: GamePrivacy = GamePrivacy.PUBLIC,
                         mode: GameMode = GameMode.MULTIPLAYER,
                         difficulty: GameDifficulty = GameDifficulty.MEDIUM,
                         max_players: int = 4, min_players: int = 2,
                         settings: Optional[Dict] = None,
                         chat_id: Optional[str] = None,
                         group_id: Optional[str] = None,
                         project_id: Optional[str] = None,
                         duration: Optional[timedelta] = None,
                         is_recurring: bool = False,
                         recurrence_pattern: Optional[str] = None,
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """Создание новой игры"""
        game_id = str(uuid.uuid4())

        game = Game(
            id=game_id,
            title=title,
            description=description,
            type=game_type,
            category=self._get_category_for_game_type(game_type),
            creator_id=creator_id,
            privacy=privacy,
            status=GameStatus.LOBBY,
            mode=mode,
            difficulty=difficulty,
            max_players=max_players,
            min_players=min_players,
            current_players=[creator_id],  # Создатель автоматически становится участником
            settings=settings or {},
            chat_id=chat_id,
            group_id=group_id,
            project_id=project_id,
            duration=duration,
            is_recurring=is_recurring,
            recurrence_pattern=recurrence_pattern,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        # Проверяем права на создание игры
        if not await self._can_create_game(game, creator_id):
            return None

        # Сохраняем игру в базу данных
        await self._save_game_to_db(game)

        # Добавляем в кэш
        await self._cache_game(game)

        # Уведомляем заинтересованные стороны
        await self._notify_game_created(game)

        # Создаем запись активности
        await self._log_activity(game.id, creator_id, "created", {
            "title": game.title,
            "type": game.type.value,
            "mode": game.mode.value
        })

        return game_id

    async def _save_game_to_db(self, game: Game):
        """Сохранение игры в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO games (
                    id, title, description, type, category, creator_id, privacy,
                    status, mode, difficulty, max_players, min_players,
                    current_players, spectators, settings, started_at, finished_at,
                    duration, chat_id, group_id, project_id, is_recurring,
                    recurrence_pattern, next_occurrence, metadata, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                         $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                         $23, $24, $25, $26, $27)
                """,
                game.id, game.title, game.description, game.type.value,
                game.category.value, game.creator_id, game.privacy.value,
                game.status.value, game.mode.value, game.difficulty.value,
                game.max_players, game.min_players, game.current_players,
                game.spectators, json.dumps(game.settings), game.started_at,
                game.finished_at, game.duration, game.chat_id, game.group_id,
                game.project_id, game.is_recurring, game.recurrence_pattern,
                game.next_occurrence, json.dumps(game.metadata) if game.metadata else None,
                game.created_at, game.updated_at
            )

    async def get_game(self, game_id: str, user_id: Optional[int] = None) -> Optional[Game]:
        """Получение игры по ID"""
        # Сначала проверяем кэш
        cached_game = await self._get_cached_game(game_id)
        if cached_game:
            # Проверяем права доступа
            if await self._can_access_game(cached_game, user_id):
                return cached_game
            else:
                return None

        # Затем базу данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, description, type, category, creator_id, privacy,
                       status, mode, difficulty, max_players, min_players,
                       current_players, spectators, settings, started_at, finished_at,
                       duration, chat_id, group_id, project_id, is_recurring,
                       recurrence_pattern, next_occurrence, metadata, created_at, updated_at
                FROM games WHERE id = $1
                """,
                game_id
            )

        if not row:
            return None

        game = Game(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            type=GameType(row['type']),
            category=GameCategory(row['category']),
            creator_id=row['creator_id'],
            privacy=GamePrivacy(row['privacy']),
            status=GameStatus(row['status']),
            mode=GameMode(row['mode']),
            difficulty=GameDifficulty(row['difficulty']),
            max_players=row['max_players'],
            min_players=row['min_players'],
            current_players=row['current_players'] or [],
            spectators=row['spectators'] or [],
            settings=json.loads(row['settings']) if row['settings'] else {},
            started_at=row['started_at'],
            finished_at=row['finished_at'],
            duration=row['duration'],
            chat_id=row['chat_id'],
            group_id=row['group_id'],
            project_id=row['project_id'],
            is_recurring=row['is_recurring'],
            recurrence_pattern=row['recurrence_pattern'],
            next_occurrence=row['next_occurrence'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Проверяем права доступа
        if not await self._can_access_game(game, user_id):
            return None

        # Кэшируем игру
        await self._cache_game(game)

        return game

    async def join_game(self, game_id: str, user_id: int) -> bool:
        """Присоединение к игре"""
        game = await self.get_game(game_id)
        if not game:
            return False

        # Проверяем статус игры
        if game.status != GameStatus.LOBBY:
            return False

        # Проверяем права на присоединение
        if not await self._can_join_game(game, user_id):
            return False

        # Проверяем лимит игроков
        if len(game.current_players) >= game.max_players:
            return False

        # Добавляем пользователя к игре
        if user_id not in game.current_players:
            game.current_players.append(user_id)
            game.updated_at = datetime.utcnow()

            # Обновляем в базе данных
            await self._update_game_in_db(game)

            # Обновляем кэш
            await self._cache_game(game)

            # Уведомляем участников
            await self._notify_player_joined(game, user_id)

            # Создаем запись активности
            await self._log_activity(game.id, user_id, "joined", {
                "player_count": len(game.current_players)
            })

            # Если набрано минимальное количество игроков, начинаем игру
            if len(game.current_players) >= game.min_players and game.auto_start:
                await self.start_game(game.id, game.creator_id)

            return True

        return False

    async def start_game(self, game_id: str, user_id: int) -> bool:
        """Начало игры"""
        game = await self.get_game(game_id, user_id)
        if not game:
            return False

        # Проверяем права на начало игры
        if not await self._can_start_game(game, user_id):
            return False

        # Проверяем минимальное количество игроков
        if len(game.current_players) < game.min_players:
            return False

        # Создаем игровую сессию
        session_id = await self._create_game_session(game)

        if session_id:
            # Обновляем статус игры
            game.status = GameStatus.STARTING
            game.started_at = datetime.utcnow()
            game.updated_at = datetime.utcnow()

            # Обновляем в базе данных
            await self._update_game_in_db(game)

            # Обновляем кэш
            await self._cache_game(game)

            # Уведомляем участников
            await self._notify_game_started(game)

            # Создаем запись активности
            await self._log_activity(game.id, user_id, "started", {
                "player_count": len(game.current_players),
                "session_id": session_id
            })

            return True

        return False

    async def _create_game_session(self, game: Game) -> Optional[str]:
        """Создание игровой сессии"""
        session_id = str(uuid.uuid4())

        # Инициализируем игроков
        players = []
        for player_id in game.current_players:
            players.append({
                'user_id': player_id,
                'score': 0,
                'status': 'active',
                'joined_at': datetime.utcnow()
            })

        session = GameSession(
            id=session_id,
            game_id=game.id,
            players=players,
            current_round=1,
            total_rounds=game.settings.get('rounds', 1),
            started_at=datetime.utcnow(),
            game_state=self._initialize_game_state(game),
            scores={pid: 0 for pid in game.current_players},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Сохраняем сессию в базу данных
        await self._save_game_session_to_db(session)

        # Добавляем в кэш
        await self._cache_game_session(session)

        # Добавляем в активные игры
        self.active_games[session_id] = session

        return session_id

    def _initialize_game_state(self, game: Game) -> Dict[str, Any]:
        """Инициализация состояния игры"""
        # Это будет зависеть от типа игры
        # В реальной системе здесь будет вызов специфичного метода для каждого типа игры
        return {
            'current_round': 1,
            'round_data': {},
            'game_specific_state': {}
        }

    async def make_move(self, session_id: str, user_id: int, move_type: str, 
                       move_data: Dict[str, Any]) -> bool:
        """Совершение хода в игре"""
        session = await self._get_game_session(session_id)
        if not session:
            return False

        game = await self.get_game(session.game_id)
        if not game:
            return False

        # Проверяем, является ли пользователь участником игры
        player_info = next((p for p in session.players if p['user_id'] == user_id), None)
        if not player_info or player_info['status'] != 'active':
            return False

        # Проверяем, чей сейчас ход (для игр с поочередными ходами)
        if game.settings.get('turn_based', False):
            if await self._is_not_player_turn(session, user_id):
                return False

        # Создаем запись хода
        move_id = str(uuid.uuid4())
        move = GameMove(
            id=move_id,
            game_session_id=session_id,
            player_id=user_id,
            move_type=move_type,
            move_data=move_data,
            timestamp=datetime.utcnow()
        )

        # Сохраняем ход
        await self._save_move_to_db(move)

        # Обновляем состояние игры
        await self._update_game_state(session, move)

        # Проверяем, завершена ли игра
        if await self._is_game_over(session):
            await self._finish_game_session(session)

        # Уведомляем участников
        await self._notify_move_made(session, move)

        # Создаем запись активности
        await self._log_activity(session.game_id, user_id, "move_made", {
            "move_type": move_type,
            "session_id": session_id
        })

        return True

    async def _update_game_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры после хода"""
        # Обновляем историю ходов
        session.move_history.append(move)

        # В зависимости от типа игры вызываем соответствующую логику
        if session.game_type == GameType.TIC_TAC_TOE:
            await self._update_tic_tac_toe_state(session, move)
        elif session.game_type == GameType.CHESS:
            await self._update_chess_state(session, move)
        elif session.game_type == GameType.CHECKERS:
            await self._update_checkers_state(session, move)
        elif session.game_type == GameType.HANGMAN:
            await self._update_hangman_state(session, move)
        elif session.game_type == GameType.TRIVIA:
            await self._update_trivia_state(session, move)
        elif session.game_type == GameType.WORD_SEARCH:
            await self._update_word_search_state(session, move)
        elif session.game_type == GameType.POKER:
            await self._update_poker_state(session, move)
        elif session.game_type == GameType.BLACKJACK:
            await self._update_blackjack_state(session, move)
        else:
            # Для нестандартных типов игр обновляем общий статус
            session.last_move_at = datetime.utcnow()
            session.current_player_index = (session.current_player_index + 1) % len(session.players)

        # Обновляем время последней активности
        session.last_activity_at = datetime.utcnow()

        # Сохраняем обновленное состояние игры
        await self._save_game_session(session)

        # Проверяем, завершена ли игра
        if await self._is_game_over(session):
            await self._finish_game_session(session)

        # Уведомляем участников об обновлении
        await self._notify_players_of_update(session)

    async def _update_tic_tac_toe_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры крестики-нолики"""
        # Проверяем, допустим ли ход
        if not self._is_valid_tic_tac_toe_move(session, move):
            raise ValueError("Invalid move in Tic Tac Toe")

        # Обновляем игровое поле
        row, col = move.position
        session.game_state['board'][row][col] = move.player_id

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

        # Увеличиваем счетчик ходов
        session.game_state['move_count'] = session.game_state.get('move_count', 0) + 1

    def _is_valid_tic_tac_toe_move(self, session: GameSession, move: GameMove) -> bool:
        """Проверка допустимости хода в крестики-нолики"""
        if not hasattr(move, 'position') or len(move.position) != 2:
            return False

        row, col = move.position
        if row < 0 or row > 2 or col < 0 or col > 2:
            return False

        # Проверяем, что клетка свободна
        board = session.game_state.get('board', [[None, None, None] for _ in range(3)])
        return board[row][col] is None

    async def _update_chess_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры шахматы"""
        # В реальной системе здесь будет сложная логика шахмат
        # Проверка допустимости хода, перемещение фигур, проверка на шах и т.д.

        # Обновляем историю ходов
        chess_moves = session.game_state.get('moves', [])
        chess_moves.append({
            'player_id': move.player_id,
            'from': move.position[0] if hasattr(move, 'position') and move.position else None,
            'to': move.position[1] if hasattr(move, 'position') and len(move.position) > 1 else None,
            'piece': move.piece if hasattr(move, 'piece') else None,
            'timestamp': datetime.utcnow().isoformat()
        })
        session.game_state['moves'] = chess_moves

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

    async def _update_checkers_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры шашки"""
        # Обновляем состояние доски
        checkers_moves = session.game_state.get('moves', [])
        checkers_moves.append({
            'player_id': move.player_id,
            'from': move.position[0] if hasattr(move, 'position') and move.position else None,
            'to': move.position[1] if hasattr(move, 'position') and len(move.position) > 1 else None,
            'captured': move.captured_pieces if hasattr(move, 'captured_pieces') else [],
            'timestamp': datetime.utcnow().isoformat()
        })
        session.game_state['moves'] = checkers_moves

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

    async def _update_hangman_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры виселица"""
        # Проверяем букву, предложенную игроком
        guess = move.action_data.get('letter', '').lower() if move.action_data else ''

        if not guess or len(guess) != 1:
            raise ValueError("Invalid letter guess in Hangman")

        # Получаем текущее состояние игры
        word = session.game_state.get('word', '').lower()
        guessed_letters = session.game_state.get('guessed_letters', [])
        incorrect_guesses = session.game_state.get('incorrect_guesses', 0)

        # Проверяем, угадана ли буква
        if guess in word and guess not in guessed_letters:
            guessed_letters.append(guess)
            session.game_state['guessed_letters'] = guessed_letters
        elif guess not in guessed_letters:
            # Неверная догадка
            incorrect_guesses += 1
            session.game_state['incorrect_guesses'] = incorrect_guesses
            session.game_state['wrong_letters'] = session.game_state.get('wrong_letters', []) + [guess]

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

    async def _update_trivia_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры викторина"""
        # Проверяем ответ на вопрос
        current_question = session.game_state.get('current_question', {})
        correct_answer = current_question.get('correct_answer')
        player_answer = move.action_data.get('answer') if move.action_data else None

        # Проверяем, правильный ли ответ
        is_correct = player_answer == correct_answer
        player_results = session.game_state.get('player_results', {})
        player_results[move.player_id] = player_results.get(move.player_id, [])
        player_results[move.player_id].append({
            'question_id': current_question.get('id'),
            'answer': player_answer,
            'is_correct': is_correct,
            'timestamp': datetime.utcnow().isoformat()
        })
        session.game_state['player_results'] = player_results

        # Обновляем счет игрока, если ответ правильный
        if is_correct:
            player_scores = session.game_state.get('player_scores', {})
            player_scores[move.player_id] = player_scores.get(move.player_id, 0) + 10
            session.game_state['player_scores'] = player_scores

        # Переходим к следующему вопросу
        session.game_state['current_question_index'] = session.game_state.get('current_question_index', 0) + 1

    async def _update_word_search_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры поиск слов"""
        # Проверяем найденное слово
        found_word = move.action_data.get('word', '').upper() if move.action_data else ''
        found_words = session.game_state.get('found_words', [])

        if found_word and found_word not in found_words:
            found_words.append(found_word)
            session.game_state['found_words'] = found_words

            # Обновляем счет
            player_scores = session.game_state.get('player_scores', {})
            player_scores[move.player_id] = player_scores.get(move.player_id, 0) + 5
            session.game_state['player_scores'] = player_scores

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

    async def _update_poker_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры покер"""
        # Обновляем действие игрока
        poker_actions = session.game_state.get('actions', [])
        poker_actions.append({
            'player_id': move.player_id,
            'action': move.action_type,
            'amount': move.amount if hasattr(move, 'amount') else 0,
            'timestamp': datetime.utcnow().isoformat()
        })
        session.game_state['actions'] = poker_actions

        # Обновляем индекс текущего игрока
        session.current_player_index = (session.current_player_index + 1) % len(session.players)

    async def _update_blackjack_state(self, session: GameSession, move: GameMove):
        """Обновление состояния игры блэкджек"""
        # Обновляем действия игрока
        blackjack_actions = session.game_state.get('player_actions', {})
        player_actions = blackjack_actions.get(move.player_id, [])
        player_actions.append({
            'action': move.action_type,
            'timestamp': datetime.utcnow().isoformat()
        })
        blackjack_actions[move.player_id] = player_actions
        session.game_state['player_actions'] = blackjack_actions

        # Если игрок сказал "hit", даем ему карту
        if move.action_type == 'hit':
            deck = session.game_state.get('deck', [])
            if deck:
                new_card = deck.pop()
                player_cards = session.game_state.get('player_cards', {})
                player_hand = player_cards.get(move.player_id, [])
                player_hand.append(new_card)
                player_cards[move.player_id] = player_hand
                session.game_state['player_cards'] = player_cards
                session.game_state['deck'] = deck

    async def _notify_players_of_update(self, session: GameSession):
        """Уведомление игроков об обновлении состояния игры"""
        # Подготовим данные для уведомления
        game_update = {
            'type': 'game_state_update',
            'session_id': session.id,
            'game_type': session.game_type.value,
            'game_state': session.game_state,
            'current_player_index': session.current_player_index,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление каждому игроку
        for player in session.players:
            await redis_client.publish(f"game:{session.id}:player:{player.id}", json.dumps(game_update))

        # Отправляем в общий канал игры
        await redis_client.publish(f"game:{session.id}:updates", json.dumps(game_update))

    async def _is_game_over(self, session: GameSession) -> bool:
        """Проверка, завершена ли игра"""
        # Это будет зависеть от типа игры
        # В реальной системе здесь будет вызов специфичного метода для каждого типа игры
        return (session.current_round >= session.total_rounds or
                len([p for p in session.players if p['status'] == 'active']) <= 1)

    async def _finish_game_session(self, session: GameSession):
        """Завершение игровой сессии"""
        session.status = GameStatus.FINISHED
        session.ended_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()

        # Вычисляем финальные результаты
        final_scores = await self._calculate_final_scores(session)
        session.leaderboards = await self._create_leaderboard(session, final_scores)

        # Обновляем в базе данных
        await self._update_game_session_in_db(session)

        # Обновляем кэш
        await self._cache_game_session(session)

        # Удаляем из активных игр
        if session.id in self.active_games:
            del self.active_games[session.id]

        # Обновляем статистику игроков
        await self._update_player_statistics(session)

        # Начисляем достижения
        await self._award_achievements(session)

        # Уведомляем участников
        await self._notify_game_finished(session)

        # Создаем запись активности
        await self._log_activity(session.game_id, session.players[0]['user_id'], "game_finished", {
            "session_id": session.id,
            "winner": session.leaderboards[0]['user_id'] if session.leaderboards else None
        })

    async def _calculate_final_scores(self, session: GameSession) -> Dict[int, int]:
        """Вычисление финальных результатов"""
        # Это будет зависеть от типа игры
        # В реальной системе здесь будет вызов специфичного метода для каждого типа игры
        return session.scores

    async def _create_leaderboard(self, session: GameSession, scores: Dict[int, int]) -> List[Dict[str, Any]]:
        """Создание таблицы лидеров"""
        leaderboard = []
        
        # Получаем имена пользователей
        user_ids = list(scores.keys())
        usernames = await self._get_usernames(user_ids)

        # Создаем записи таблицы лидеров
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (user_id, score) in enumerate(sorted_scores, 1):
            leaderboard.append({
                'user_id': user_id,
                'username': usernames.get(user_id, f"User {user_id}"),
                'score': score,
                'rank': rank
            })

        return leaderboard

    async def _get_usernames(self, user_ids: List[int]) -> Dict[int, str]:
        """Получение имен пользователей по ID"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, username FROM users WHERE id = ANY($1)",
                user_ids
            )

        return {row['id']: row['username'] for row in rows}

    async def _update_player_statistics(self, session: GameSession):
        """Обновление статистики игроков"""
        for player_data in session.players:
            user_id = player_data['user_id']
            score = session.scores.get(user_id, 0)
            
            # Обновляем статистику в базе данных
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO player_statistics (user_id, games_played, total_score, last_played)
                    VALUES ($1, 1, $2, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        games_played = player_statistics.games_played + 1,
                        total_score = player_statistics.total_score + $2,
                        last_played = $3
                    """,
                    user_id, score, datetime.utcnow()
                )

    async def _award_achievements(self, session: GameSession):
        """Начисление достижений"""
        for player_data in session.players:
            user_id = player_data['user_id']
            
            # Проверяем и начисляем достижения
            await self._check_and_award_first_win(user_id, session)
            await self._check_and_award_quiz_master(user_id, session)
            # Добавьте другие проверки достижений

    async def _check_and_award_first_win(self, user_id: int, session: GameSession):
        """Проверка и начисление достижения за первую победу"""
        # Проверяем, является ли это первой победой пользователя
        async with db_pool.acquire() as conn:
            win_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM game_sessions gs
                JOIN game_leaderboards gl ON gs.id = gl.session_id
                WHERE gl.user_id = $1 AND gl.rank = 1 AND gs.ended_at IS NOT NULL
                """,
                user_id
            )

        if win_count == 1:  # Это первая победа
            await self._award_achievement(user_id, 'first_win')

    async def _award_achievement(self, user_id: int, achievement_type: str):
        """Начисление достижения пользователю"""
        achievement_data = self.achievements_registry.get(achievement_type)
        if not achievement_data:
            return

        achievement_id = str(uuid.uuid4())
        achievement = GameAchievement(
            id=achievement_id,
            user_id=user_id,
            achievement_type=achievement_type,
            name=achievement_data['name'],
            description=achievement_data['description'],
            points=achievement_data['points'],
            unlocked_at=datetime.utcnow()
        )

        # Сохраняем достижение в базу данных
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO game_achievements (id, user_id, achievement_type, name, description, points, unlocked_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                achievement.id, achievement.user_id, achievement.achievement_type,
                achievement.name, achievement.description, achievement.points,
                achievement.unlocked_at
            )

        # Уведомляем пользователя
        await self._notify_achievement_unlocked(user_id, achievement)

    async def _notify_achievement_unlocked(self, user_id: int, achievement: GameAchievement):
        """Уведомление пользователя о новом достижении"""
        notification = {
            'type': 'achievement_unlocked',
            'achievement': {
                'id': achievement.id,
                'name': achievement.name,
                'description': achievement.description,
                'points': achievement.points
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(user_id, notification)

    async def get_user_games(self, user_id: int, status: Optional[GameStatus] = None,
                           game_type: Optional[GameType] = None,
                           limit: int = 50, offset: int = 0) -> List[Game]:
        """Получение игр пользователя"""
        conditions = ["($1 = ANY(current_players) OR creator_id = $1)"]
        params = [user_id]
        param_idx = 2

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if game_type:
            conditions.append(f"type = ${param_idx}")
            params.append(game_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        sql_query = f"""
            SELECT id, title, description, type, category, creator_id, privacy,
                   status, mode, difficulty, max_players, min_players,
                   current_players, spectators, settings, started_at, finished_at,
                   duration, chat_id, group_id, project_id, is_recurring,
                   recurrence_pattern, next_occurrence, metadata, created_at, updated_at
            FROM games
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        params.extend([limit, offset])

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, *params)

        games = []
        for row in rows:
            game = Game(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                type=GameType(row['type']),
                category=GameCategory(row['category']),
                creator_id=row['creator_id'],
                privacy=GamePrivacy(row['privacy']),
                status=GameStatus(row['status']),
                mode=GameMode(row['mode']),
                difficulty=GameDifficulty(row['difficulty']),
                max_players=row['max_players'],
                min_players=row['min_players'],
                current_players=row['current_players'] or [],
                spectators=row['spectators'] or [],
                settings=json.loads(row['settings']) if row['settings'] else {},
                started_at=row['started_at'],
                finished_at=row['finished_at'],
                duration=row['duration'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                is_recurring=row['is_recurring'],
                recurrence_pattern=row['recurrence_pattern'],
                next_occurrence=row['next_occurrence'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            games.append(game)

        return games

    async def get_active_games(self, user_id: int) -> List[Game]:
        """Получение активных игр пользователя"""
        sql_query = """
            SELECT id, title, description, type, category, creator_id, privacy,
                   status, mode, difficulty, max_players, min_players,
                   current_players, spectators, settings, started_at, finished_at,
                   duration, chat_id, group_id, project_id, is_recurring,
                   recurrence_pattern, next_occurrence, metadata, created_at, updated_at
            FROM games
            WHERE $1 = ANY(current_players) AND status IN ('lobby', 'starting', 'in_progress')
            ORDER BY created_at DESC
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, user_id)

        games = []
        for row in rows:
            game = Game(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                type=GameType(row['type']),
                category=GameCategory(row['category']),
                creator_id=row['creator_id'],
                privacy=GamePrivacy(row['privacy']),
                status=GameStatus(row['status']),
                mode=GameMode(row['mode']),
                difficulty=GameDifficulty(row['difficulty']),
                max_players=row['max_players'],
                min_players=row['min_players'],
                current_players=row['current_players'] or [],
                spectators=row['spectators'] or [],
                settings=json.loads(row['settings']) if row['settings'] else {},
                started_at=row['started_at'],
                finished_at=row['finished_at'],
                duration=row['duration'],
                chat_id=row['chat_id'],
                group_id=row['group_id'],
                project_id=row['project_id'],
                is_recurring=row['is_recurring'],
                recurrence_pattern=row['recurrence_pattern'],
                next_occurrence=row['next_occurrence'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            games.append(game)

        return games

    async def get_game_leaderboard(self, game_id: str, limit: int = 10, 
                                 offset: int = 0) -> List[GameLeaderboardEntry]:
        """Получение таблицы лидеров игры"""
        sql_query = """
            SELECT u.id as user_id, u.username, gs.score, gs.games_played, gs.games_won,
                   (CASE WHEN gs.games_played > 0 THEN (gs.games_won::FLOAT / gs.games_played) ELSE 0 END) as win_rate,
                   gs.last_played
            FROM game_statistics gs
            JOIN users u ON gs.user_id = u.id
            WHERE gs.game_type = (SELECT type FROM games WHERE id = $1)
            ORDER BY gs.score DESC, gs.last_played DESC
            LIMIT $2 OFFSET $3
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql_query, game_id, limit, offset)

        leaderboard = []
        for i, row in enumerate(rows, start=offset + 1):
            entry = GameLeaderboardEntry(
                user_id=row['user_id'],
                username=row['username'],
                score=row['score'],
                rank=i,
                games_played=row['games_played'],
                games_won=row['games_won'],
                win_rate=row['win_rate'],
                last_played=row['last_played']
            )
            leaderboard.append(entry)

        return leaderboard

    async def send_game_invite(self, game_id: str, inviter_id: int, 
                             invitee_id: int, expires_in_minutes: int = 1440) -> Optional[str]:
        """Отправка приглашения в игру"""
        game = await self.get_game(game_id)
        if not game:
            return None

        # Проверяем права на отправку приглашения
        if not await self._can_invite_to_game(game, inviter_id):
            return None

        invite_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

        invite = GameInvite(
            id=invite_id,
            game_id=game_id,
            inviter_id=inviter_id,
            invitee_id=invitee_id,
            status='pending',
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )

        # Сохраняем приглашение в базу данных
        await self._save_invite_to_db(invite)

        # Добавляем в кэш
        await self._cache_invite(invite)

        # Уведомляем приглашенного пользователя
        await self._notify_game_invite(invite)

        # Создаем запись активности
        await self._log_activity(game_id, inviter_id, "invite_sent", {
            "invitee_id": invitee_id,
            "expires_at": expires_at.isoformat()
        })

        return invite_id

    async def _save_invite_to_db(self, invite: GameInvite):
        """Сохранение приглашения в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO game_invites (id, game_id, inviter_id, invitee_id, status, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                invite.id, invite.game_id, invite.inviter_id,
                invite.invitee_id, invite.status, invite.created_at, invite.expires_at
            )

    async def _notify_game_invite(self, invite: GameInvite):
        """Уведомление о приглашении в игру"""
        game = await self.get_game(invite.game_id)

        notification = {
            'type': 'game_invite',
            'invite': {
                'id': invite.id,
                'game_id': invite.game_id,
                'game_title': game.title if game else 'Unknown Game',
                'inviter_id': invite.inviter_id,
                'expires_at': invite.expires_at.isoformat() if invite.expires_at else None
            },
            'timestamp': datetime.utcnow().isoformat()
        }

        await self._send_notification_to_user(invite.invitee_id, notification)

    async def _can_create_game(self, game: Game, user_id: int) -> bool:
        """Проверка прав на создание игры"""
        # Проверяем, может ли пользователь создать игру в указанном чате/группе
        if game.chat_id:
            return await self._can_access_chat(game.chat_id, user_id)
        elif game.group_id:
            return await self._is_group_member(user_id, game.group_id)
        elif game.project_id:
            return await self._is_project_member(user_id, game.project_id)
        else:
            # Личная игра - может создать любой пользователь
            return True

    async def _can_join_game(self, game: Game, user_id: int) -> bool:
        """Проверка прав на присоединение к игре"""
        if game.privacy == GamePrivacy.PUBLIC:
            return True
        elif game.privacy == GamePrivacy.FRIENDS_ONLY:
            return await self._are_friends(game.creator_id, user_id)
        elif game.privacy == GamePrivacy.GROUP_MEMBERS:
            if game.group_id:
                return await self._is_group_member(user_id, game.group_id)
            return False
        elif game.privacy == GamePrivacy.INVITE_ONLY:
            # Проверяем, есть ли приглашение
            invite = await self._get_pending_invite(game.id, user_id)
            return invite is not None
        else:
            return game.creator_id == user_id

    async def _can_start_game(self, game: Game, user_id: int) -> bool:
        """Проверка прав на начало игры"""
        # Только создатель игры может начать
        return game.creator_id == user_id

    async def _can_invite_to_game(self, game: Game, user_id: int) -> bool:
        """Проверка прав на приглашение в игру"""
        # Создатель игры или администратор чата/группы может приглашать
        if game.creator_id == user_id:
            return True

        if game.chat_id:
            return await self._is_chat_admin(game.chat_id, user_id)

        if game.group_id:
            return await self._is_group_admin(game.group_id, user_id)

        return False

    async def _can_access_game(self, game: Game, user_id: Optional[int]) -> bool:
        """Проверка прав на доступ к игре"""
        if game.privacy == GamePrivacy.PUBLIC:
            return True

        if not user_id:
            return False

        if game.creator_id == user_id:
            return True

        if user_id in game.current_players:
            return True

        if game.privacy == GamePrivacy.FRIENDS_ONLY:
            return await self._are_friends(game.creator_id, user_id)

        if game.privacy == GamePrivacy.GROUP_MEMBERS:
            if game.group_id:
                return await self._is_group_member(user_id, game.group_id)
            return False

        if game.privacy == GamePrivacy.INVITE_ONLY:
            invite = await self._get_pending_invite(game.id, user_id)
            return invite is not None

        return False

    async def _get_cached_game(self, game_id: str) -> Optional[Game]:
        """Получение игры из кэша"""
        cached = await redis_client.get(f"game:{game_id}")
        if cached:
            return Game(**json.loads(cached))
        return None

    async def _cache_game(self, game: Game):
        """Кэширование игры"""
        await redis_client.setex(f"game:{game.id}", 300, game.model_dump_json())

    async def _get_game_session(self, session_id: str) -> Optional[GameSession]:
        """Получение игровой сессии"""
        # Сначала из кэша
        cached = await redis_client.get(f"game_session:{session_id}")
        if cached:
            return GameSession(**json.loads(cached))

        # Затем из базы данных
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, game_id, players, current_round, total_rounds,
                       started_at, ended_at, game_state, scores, leaderboards,
                       chat_id, created_at, updated_at
                FROM game_sessions WHERE id = $1
                """,
                session_id
            )

        if not row:
            return None

        session = GameSession(
            id=row['id'],
            game_id=row['game_id'],
            players=json.loads(row['players']) if row['players'] else [],
            current_round=row['current_round'],
            total_rounds=row['total_rounds'],
            started_at=row['started_at'],
            ended_at=row['ended_at'],
            game_state=json.loads(row['game_state']) if row['game_state'] else {},
            scores=json.loads(row['scores']) if row['scores'] else {},
            leaderboards=json.loads(row['leaderboards']) if row['leaderboards'] else [],
            chat_id=row['chat_id'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

        # Кэшируем сессию
        await self._cache_game_session(session)

        return session

    async def _cache_game_session(self, session: GameSession):
        """Кэширование игровой сессии"""
        await redis_client.setex(f"game_session:{session.id}", 300, session.model_dump_json())

    async def _save_game_session_to_db(self, session: GameSession):
        """Сохранение игровой сессии в базу данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO game_sessions (
                    id, game_id, players, current_round, total_rounds,
                    started_at, ended_at, game_state, scores, leaderboards,
                    chat_id, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                session.id, session.game_id, json.dumps(session.players),
                session.current_round, session.total_rounds, session.started_at,
                session.ended_at, json.dumps(session.game_state),
                json.dumps(session.scores), json.dumps(session.leaderboards),
                session.chat_id, session.created_at, session.updated_at
            )

    async def _update_game_session_in_db(self, session: GameSession):
        """Обновление игровой сессии в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE game_sessions SET
                    players = $2, current_round = $3, total_rounds = $4,
                    started_at = $5, ended_at = $6, game_state = $7,
                    scores = $8, leaderboards = $9, updated_at = $10
                WHERE id = $1
                """,
                session.id, json.dumps(session.players), session.current_round,
                session.total_rounds, session.started_at, session.ended_at,
                json.dumps(session.game_state), json.dumps(session.scores),
                json.dumps(session.leaderboards), session.updated_at
            )

    async def _update_game_in_db(self, game: Game):
        """Обновление игры в базе данных"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE games SET
                    current_players = $2, spectators = $3, status = $4,
                    started_at = $5, finished_at = $6, updated_at = $7
                WHERE id = $1
                """,
                game.id, game.current_players, game.spectators, 
                game.status.value, game.started_at, game.finished_at, game.updated_at
            )

    async def _notify_game_created(self, game: Game):
        """Уведомление о создании игры"""
        notification = {
            'type': 'game_created',
            'game': self._game_to_dict(game),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем уведомление создателю
        await self._send_notification_to_user(game.creator_id, notification)

        # Если игра связана с чатом, отправляем в чат
        if game.chat_id:
            await self._send_notification_to_chat(game.chat_id, notification)

    async def _notify_player_joined(self, game: Game, user_id: int):
        """Уведомление о присоединении игрока"""
        notification = {
            'type': 'player_joined',
            'game_id': game.id,
            'game_title': game.title,
            'user_id': user_id,
            'player_count': len(game.current_players),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам игры
        for player_id in game.current_players:
            if player_id != user_id:  # Не отправляем самому присоединившемуся
                await self._send_notification_to_user(player_id, notification)

        # Если игра связана с чатом, отправляем в чат
        if game.chat_id:
            await self._send_notification_to_chat(game.chat_id, notification)

    async def _notify_game_started(self, game: Game):
        """Уведомление о начале игры"""
        notification = {
            'type': 'game_started',
            'game': self._game_to_dict(game),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам игры
        for player_id in game.current_players:
            await self._send_notification_to_user(player_id, notification)

        # Если игра связана с чатом, отправляем в чат
        if game.chat_id:
            await self._send_notification_to_chat(game.chat_id, notification)

    async def _notify_move_made(self, session: GameSession, move: GameMove):
        """Уведомление о совершенном ходе"""
        notification = {
            'type': 'move_made',
            'session_id': session.id,
            'game_id': session.game_id,
            'player_id': move.player_id,
            'move_type': move.move_type,
            'move_data': move.move_data,
            'timestamp': move.timestamp.isoformat()
        }

        # Отправляем всем участникам сессии
        for player in session.players:
            if player['user_id'] != move.player_id:  # Не отправляем самому совершившему ход
                await self._send_notification_to_user(player['user_id'], notification)

        # Если сессия связана с чатом, отправляем в чат
        if session.chat_id:
            await self._send_notification_to_chat(session.chat_id, notification)

    async def _notify_game_finished(self, session: GameSession):
        """Уведомление о завершении игры"""
        game = await self.get_game(session.game_id)

        notification = {
            'type': 'game_finished',
            'session_id': session.id,
            'game_id': session.game_id,
            'game_title': game.title if game else 'Unknown Game',
            'leaderboard': session.leaderboards,
            'duration': (session.ended_at - session.started_at).total_seconds() if session.ended_at and session.started_at else None,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Отправляем всем участникам сессии
        for player in session.players:
            await self._send_notification_to_user(player['user_id'], notification)

        # Если сессия связана с чатом, отправляем в чат
        if session.chat_id:
            await self._send_notification_to_chat(session.chat_id, notification)

    def _game_to_dict(self, game: Game) -> Dict[str, Any]:
        """Конвертация игры в словарь для уведомлений"""
        return {
            'id': game.id,
            'title': game.title,
            'description': game.description,
            'type': game.type.value,
            'category': game.category.value,
            'creator_id': game.creator_id,
            'privacy': game.privacy.value,
            'status': game.status.value,
            'mode': game.mode.value,
            'difficulty': game.difficulty.value,
            'max_players': game.max_players,
            'min_players': game.min_players,
            'current_player_count': len(game.current_players),
            'started_at': game.started_at.isoformat() if game.started_at else None,
            'created_at': game.created_at.isoformat() if game.created_at else None,
            'chat_id': game.chat_id,
            'group_id': game.group_id,
            'project_id': game.project_id
        }

    async def _send_notification_to_user(self, user_id: int, notification: Dict[str, Any]):
        """Отправка уведомления пользователю"""
        channel = f"user:{user_id}:games"
        await redis_client.publish(channel, json.dumps(notification))

    async def _send_notification_to_chat(self, chat_id: str, notification: Dict[str, Any]):
        """Отправка уведомления в чат"""
        channel = f"chat:{chat_id}:games"
        await redis_client.publish(channel, json.dumps(notification))

    async def _log_activity(self, game_id: str, user_id: int, action: str, details: Dict[str, Any]):
        """Логирование игровой активности"""
        activity_id = str(uuid.uuid4())
        activity = {
            'id': activity_id,
            'game_id': game_id,
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Сохраняем в Redis для быстрого доступа
        await redis_client.lpush(f"game_activities:{game_id}", json.dumps(activity))
        await redis_client.ltrim(f"game_activities:{game_id}", 0, 99)  # Храним последние 100 активностей

    async def _get_pending_invite(self, game_id: str, user_id: int) -> Optional[GameInvite]:
        """Получение ожидающего приглашения"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, game_id, inviter_id, invitee_id, status, created_at, expires_at
                FROM game_invites
                WHERE game_id = $1 AND invitee_id = $2 AND status = 'pending'
                AND (expires_at IS NULL OR expires_at > $3)
                """,
                game_id, user_id, datetime.utcnow()
            )

        if not row:
            return None

        return GameInvite(
            id=row['id'],
            game_id=row['game_id'],
            inviter_id=row['inviter_id'],
            invitee_id=row['invitee_id'],
            status=row['status'],
            created_at=row['created_at'],
            expires_at=row['expires_at']
        )

    async def _is_chat_admin(self, chat_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором чата"""
        # В реальной системе здесь будет проверка прав в чате
        return False

    async def _is_group_admin(self, group_id: str, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором группы"""
        # В реальной системе здесь будет проверка прав в группе
        return False

    async def _is_project_member(self, user_id: int, project_id: str) -> bool:
        """Проверка, является ли пользователь участником проекта"""
        # В реальной системе здесь будет проверка участия в проекте
        return False

    async def _are_friends(self, user1_id: int, user2_id: int) -> bool:
        """Проверка, являются ли пользователи друзьями"""
        # В реальной системе здесь будет проверка в таблице друзей
        return False

    async def _is_group_member(self, user_id: int, group_id: str) -> bool:
        """Проверка, является ли пользователь членом группы"""
        # В реальной системе здесь будет проверка в таблице участников группы
        return False

    def _get_category_for_game_type(self, game_type: GameType) -> GameCategory:
        """Определение категории по типу игры"""
        category_mapping = {
            GameType.TRIVIA: GameCategory.EDUCATIONAL,
            GameType.WORD_GAMES: GameCategory.BRAIN_TRAINING,
            GameType.BOARD_GAMES: GameCategory.SOCIAL,
            GameType.CARD_GAMES: GameCategory.SOCIAL,
            GameType.PUZZLES: GameCategory.BRAIN_TRAINING,
            GameType.QUIZZES: GameCategory.EDUCATIONAL,
            GameType.MINI_GAMES: GameCategory.ENTERTAINMENT,
            GameType.MULTIPLAYER_GAMES: GameCategory.COMPETITIVE,
            GameType.CASUAL_GAMES: GameCategory.ENTERTAINMENT,
            GameType.STRATEGY_GAMES: GameCategory.BRAIN_TRAINING,
            GameType.ARCADE_GAMES: GameCategory.ENTERTAINMENT
        }
        return category_mapping.get(game_type, GameCategory.ENTERTAINMENT)

    async def _can_access_chat(self, chat_id: str, user_id: int) -> bool:
        """Проверка прав доступа к чату"""
        # В реальной системе здесь будет проверка участия в чате
        return False

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
game_service = GameService()