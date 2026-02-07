# server/app/games/minigames.py
import asyncio
import json
import random
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime
from abc import ABC, abstractmethod

class GameType(Enum):
    TRIVIA = "trivia"
    TICTACTOE = "tic_tac_toe"
    HANGMAN = "hangman"
    WORD_SEARCH = "word_search"
    PUZZLE = "puzzle"

class GameState(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"
    CANCELLED = "cancelled"

@dataclass
class Player:
    user_id: int
    username: str
    score: int = 0
    is_ready: bool = False
    last_action: datetime = None

@dataclass
class GameSession:
    session_id: str
    game_type: GameType
    players: List[Player]
    max_players: int
    min_players: int
    state: GameState
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    game_data: Dict[str, Any] = None
    current_turn: int = 0
    winner: Optional[int] = None

class BaseGame(ABC):
    """Базовый класс для всех игр"""
    
    def __init__(self, session_id: str, players: List[Player]):
        self.session_id = session_id
        self.players = players
        self.game_state = GameState.WAITING
        self.game_data = {}
        self.created_at = datetime.utcnow()
    
    @abstractmethod
    async def start_game(self):
        """Начало игры"""
        raise NotImplementedError
    
    @abstractmethod
    async def make_move(self, player_id: int, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение хода игроком"""
        raise NotImplementedError
    
    @abstractmethod
    async def get_game_state(self) -> Dict[str, Any]:
        """Получение текущего состояния игры"""
        raise NotImplementedError
    
    @abstractmethod
    async def check_winner(self) -> Optional[int]:
        """Проверка победителя"""
        raise NotImplementedError

class TriviaGame(BaseGame):
    """Игра викторина"""
    
    def __init__(self, session_id: str, players: List[Player]):
        super().__init__(session_id, players)
        self.questions = [
            {
                "question": "Какой столица Франции?",
                "options": ["Лондон", "Берлин", "Париж", "Мадрид"],
                "correct": 2
            },
            {
                "question": "Сколько планет в Солнечной системе?",
                "options": ["7", "8", "9", "10"],
                "correct": 1
            },
            {
                "question": "Кто написал 'Война и мир'?",
                "options": ["Достоевский", "Толстой", "Гоголь", "Пушкин"],
                "correct": 1
            },
            {
                "question": "Какой химический символ у золота?",
                "options": ["Go", "Gd", "Au", "Ag"],
                "correct": 2
            },
            {
                "question": "Сколько сторон у шестиугольника?",
                "options": ["5", "6", "7", "8"],
                "correct": 1
            }
        ]
        self.current_question = 0
        self.player_answers = {player.user_id: None for player in self.players}
        self.question_start_time = None
    
    async def start_game(self):
        """Начало викторины"""
        self.game_state = GameState.PLAYING
        self.started_at = datetime.utcnow()
        self.current_question = 0
        self.player_answers = {player.user_id: None for player in self.players}
        self.question_start_time = datetime.utcnow()
        
        # Отправляем первый вопрос
        await self.send_current_question()
    
    async def send_current_question(self):
        """Отправка текущего вопроса игрокам"""
        if self.current_question < len(self.questions):
            question = self.questions[self.current_question]
            question_data = {
                "question_number": self.current_question + 1,
                "total_questions": len(self.questions),
                "question": question["question"],
                "options": question["options"]
            }
            
            # Отправляем вопрос всем игрокам
            for player in self.players:
                await self.send_to_player(player.user_id, {
                    "type": "trivia_question",
                    "session_id": self.session_id,
                    "question": question_data
                })
    
    async def make_move(self, player_id: int, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ответ на вопрос"""
        if self.game_state != GameState.PLAYING:
            return {"success": False, "error": "Game is not active"}
        
        if player_id not in self.player_answers:
            return {"success": False, "error": "Player not in game"}
        
        if self.player_answers[player_id] is not None:
            return {"success": False, "error": "Answer already submitted"}
        
        # Сохраняем ответ
        self.player_answers[player_id] = move_data.get("answer", -1)
        
        # Проверяем, все ли ответили или время вышло
        if all(answer is not None for answer in self.player_answers.values()) or \
           (datetime.utcnow() - self.question_start_time).seconds > 30:  # 30 секунд на ответ
            await self.process_question_result()
        
        return {"success": True}
    
    async def process_question_result(self):
        """Обработка результата вопроса"""
        correct_answer = self.questions[self.current_question]["correct"]
        
        # Проверяем ответы игроков
        for player_id, answer in self.player_answers.items():
            if answer == correct_answer:
                # Находим игрока и увеличиваем его счет
                for player in self.players:
                    if player.user_id == player_id:
                        player.score += 10  # 10 очков за правильный ответ
                        break
        
        # Подготавливаем результаты вопроса
        results = {
            "question_number": self.current_question + 1,
            "correct_answer": correct_answer,
            "player_results": {}
        }
        
        for player_id, answer in self.player_answers.items():
            results["player_results"][player_id] = {
                "submitted_answer": answer,
                "is_correct": answer == correct_answer
            }
        
        # Отправляем результаты всем игрокам
        for player in self.players:
            await self.send_to_player(player.user_id, {
                "type": "trivia_question_result",
                "session_id": self.session_id,
                "results": results
            })
        
        # Переходим к следующему вопросу или завершаем игру
        self.current_question += 1
        if self.current_question >= len(self.questions):
            await self.finish_game()
        else:
            # Немного задержки перед следующим вопросом
            await asyncio.sleep(3)
            self.player_answers = {player.user_id: None for player in self.players}
            self.question_start_time = datetime.utcnow()
            await self.send_current_question()
    
    async def get_game_state(self) -> Dict[str, Any]:
        """Получение состояния игры"""
        return {
            "session_id": self.session_id,
            "game_type": self.__class__.__name__,
            "state": self.game_state.value,
            "current_question": self.current_question,
            "total_questions": len(self.questions),
            "players": [{"user_id": p.user_id, "username": p.username, "score": p.score} for p in self.players],
            "player_answers": self.player_answers
        }
    
    async def check_winner(self) -> Optional[int]:
        """Проверка победителя"""
        if self.game_state == GameState.FINISHED:
            # Находим игрока с наибольшим количеством очков
            winner = max(self.players, key=lambda p: p.score, default=None)
            return winner.user_id if winner else None
        return None
    
    async def finish_game(self):
        """Завершение игры"""
        self.game_state = GameState.FINISHED
        self.finished_at = datetime.utcnow()
        
        # Определяем победителя
        winner_id = await self.check_winner()
        
        # Отправляем результаты игры
        results = {
            "final_scores": [{"user_id": p.user_id, "username": p.username, "score": p.score} for p in self.players],
            "winner_id": winner_id
        }
        
        for player in self.players:
            await self.send_to_player(player.user_id, {
                "type": "trivia_game_finished",
                "session_id": self.session_id,
                "results": results
            })
    
    async def send_to_player(self, player_id: int, data: Dict[str, Any]):
        """Отправка данных игроку (в реальном приложении через WebSocket/Redis)"""
        # В реальном приложении здесь будет отправка через WebSocket
        print(f"Sending to player {player_id}: {data}")

class TicTacToeGame(BaseGame):
    """Игра крестики-нолики"""
    
    def __init__(self, session_id: str, players: List[Player]):
        super().__init__(session_id, players)
        self.board = [[None for _ in range(3)] for _ in range(3)]
        self.current_player_idx = 0  # Индекс текущего игрока
        self.symbols = ["X", "O"]  # Символы для игроков
    
    async def start_game(self):
        """Начало игры"""
        self.game_state = GameState.PLAYING
        self.started_at = datetime.utcnow()
        self.board = [[None for _ in range(3)] for _ in range(3)]
        self.current_player_idx = 0
        
        # Отправляем начальное состояние игры
        await self.send_game_state_to_all()
    
    async def make_move(self, player_id: int, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение хода"""
        if self.game_state != GameState.PLAYING:
            return {"success": False, "error": "Game is not active"}
        
        # Проверяем, что ход делает текущий игрок
        current_player = self.players[self.current_player_idx]
        if current_player.user_id != player_id:
            return {"success": False, "error": "Not your turn"}
        
        # Получаем координаты хода
        row = move_data.get("row", -1)
        col = move_data.get("col", -1)
        
        if not (0 <= row <= 2 and 0 <= col <= 2):
            return {"success": False, "error": "Invalid coordinates"}
        
        if self.board[row][col] is not None:
            return {"success": False, "error": "Cell already occupied"}
        
        # Делаем ход
        symbol = self.symbols[self.current_player_idx % 2]
        self.board[row][col] = symbol
        
        # Проверяем победителя
        winner = await self.check_winner()
        if winner is not None:
            await self.handle_game_win(winner)
            return {"success": True, "game_over": True, "winner": winner}
        
        # Проверяем ничью
        if self.is_board_full():
            await self.handle_draw()
            return {"success": True, "game_over": True, "draw": True}
        
        # Переход хода следующему игроку
        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        
        # Отправляем обновленное состояние игры
        await self.send_game_state_to_all()
        
        return {"success": True}
    
    async def get_game_state(self) -> Dict[str, Any]:
        """Получение состояния игры"""
        return {
            "session_id": self.session_id,
            "game_type": self.__class__.__name__,
            "state": self.game_state.value,
            "board": self.board,
            "current_player": self.players[self.current_player_idx].user_id if len(self.players) > 0 else None,
            "players": [{"user_id": p.user_id, "username": p.username, "symbol": self.symbols[i % 2]} for i, p in enumerate(self.players)],
            "winner": await self.check_winner()
        }
    
    async def check_winner(self) -> Optional[int]:
        """Проверка победителя"""
        # Проверяем строки
        for row in range(3):
            if self.board[row][0] == self.board[row][1] == self.board[row][2] and self.board[row][0] is not None:
                symbol = self.board[row][0]
                return self.get_player_by_symbol(symbol).user_id
        
        # Проверяем столбцы
        for col in range(3):
            if self.board[0][col] == self.board[1][col] == self.board[2][col] and self.board[0][col] is not None:
                symbol = self.board[0][col]
                return self.get_player_by_symbol(symbol).user_id
        
        # Проверяем диагонали
        if self.board[0][0] == self.board[1][1] == self.board[2][2] and self.board[0][0] is not None:
            symbol = self.board[0][0]
            return self.get_player_by_symbol(symbol).user_id
        
        if self.board[0][2] == self.board[1][1] == self.board[2][0] and self.board[0][2] is not None:
            symbol = self.board[0][2]
            return self.get_player_by_symbol(symbol).user_id
        
        return None
    
    def get_player_by_symbol(self, symbol: str) -> Optional[Player]:
        """Получение игрока по символу"""
        for i, player in enumerate(self.players):
            if self.symbols[i % 2] == symbol:
                return player
        return None
    
    def is_board_full(self) -> bool:
        """Проверка, заполнена ли доска"""
        for row in self.board:
            for cell in row:
                if cell is None:
                    return False
        return True
    
    async def handle_game_win(self, winner_id: int):
        """Обработка победы"""
        self.game_state = GameState.FINISHED
        self.finished_at = datetime.utcnow()
        
        # Находим победителя и увеличиваем ему счет
        for player in self.players:
            if player.user_id == winner_id:
                player.score += 50  # 50 очков за победу
                break
        
        # Отправляем результаты
        result = {
            "winner_id": winner_id,
            "board": self.board,
            "final_scores": [{"user_id": p.user_id, "username": p.username, "score": p.score} for p in self.players]
        }
        
        for player in self.players:
            await self.send_to_player(player.user_id, {
                "type": "tictactoe_game_finished",
                "session_id": self.session_id,
                "result": result
            })
    
    async def handle_draw(self):
        """Обработка ничьей"""
        self.game_state = GameState.FINISHED
        self.finished_at = datetime.utcnow()
        
        # Отправляем результаты
        result = {
            "result": "draw",
            "board": self.board,
            "final_scores": [{"user_id": p.user_id, "username": p.username, "score": p.score} for p in self.players]
        }
        
        for player in self.players:
            await self.send_to_player(player.user_id, {
                "type": "tictactoe_game_finished",
                "session_id": self.session_id,
                "result": result
            })
    
    async def send_game_state_to_all(self):
        """Отправка состояния игры всем игрокам"""
        game_state = await self.get_game_state()
        
        for player in self.players:
            await self.send_to_player(player.user_id, {
                "type": "tictactoe_game_state",
                "session_id": self.session_id,
                "game_state": game_state
            })
    
    async def send_to_player(self, player_id: int, data: Dict[str, Any]):
        """Отправка данных игроку (в реальном приложении через WebSocket/Redis)"""
        # В реальном приложении здесь будет отправка через WebSocket
        print(f"Sending to player {player_id}: {data}")

class GameManager:
    """Менеджер игр"""
    
    def __init__(self, redis_client, db_pool):
        self.redis = redis_client
        self.db_pool = db_pool
        self.active_games: Dict[str, BaseGame] = {}
        self.player_sessions: Dict[int, str] = {}  # user_id -> session_id
        self.game_factories = {
            GameType.TRIVIA: TriviaGame,
            GameType.TICTACTOE: TicTacToeGame
        }
    
    async def create_game_session(self, game_type: GameType, creator_id: int, 
                                 player_ids: List[int], max_players: int = 2) -> str:
        """Создание игровой сессии"""
        session_id = str(uuid.uuid4())
        
        # Создаем игроков
        players = []
        async with self.db_pool.acquire() as conn:
            for user_id in player_ids:
                user_data = await conn.fetchrow(
                    "SELECT id, username FROM users WHERE id = $1",
                    user_id
                )
                if user_data:
                    players.append(Player(
                        user_id=user_data['id'],
                        username=user_data['username']
                    ))
        
        # Создаем игру
        if game_type in self.game_factories:
            game_class = self.game_factories[game_type]
            game = game_class(session_id, players)
            
            self.active_games[session_id] = game
            
            # Регистрируем игроков в сессии
            for player in players:
                self.player_sessions[player.user_id] = session_id
            
            return session_id
        else:
            raise ValueError(f"Unsupported game type: {game_type}")
    
    async def join_game(self, session_id: str, user_id: int) -> bool:
        """Присоединение к игре"""
        if session_id not in self.active_games:
            return False
        
        game = self.active_games[session_id]
        if game.game_state != GameState.WAITING:
            return False  # Нельзя присоединиться к начатой игре
        
        # Проверяем, не участвует ли пользователь уже в другой игре
        if user_id in self.player_sessions:
            return False
        
        # Добавляем пользователя в игру
        async with self.db_pool.acquire() as conn:
            user_data = await conn.fetchrow(
                "SELECT id, username FROM users WHERE id = $1",
                user_id
            )
            if user_data:
                player = Player(
                    user_id=user_data['id'],
                    username=user_data['username']
                )
                game.players.append(player)
                self.player_sessions[user_id] = session_id
                return True
        
        return False
    
    async def start_game(self, session_id: str) -> bool:
        """Начало игры"""
        if session_id not in self.active_games:
            return False
        
        game = self.active_games[session_id]
        await game.start_game()
        return True
    
    async def make_move(self, session_id: str, user_id: int, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение хода"""
        if session_id not in self.active_games:
            return {"success": False, "error": "Game session not found"}
        
        game = self.active_games[session_id]
        return await game.make_move(user_id, move_data)
    
    async def get_game_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение состояния игры"""
        if session_id not in self.active_games:
            return None
        
        game = self.active_games[session_id]
        return await game.get_game_state()
    
    async def leave_game(self, user_id: int) -> bool:
        """Покидание игры пользователем"""
        if user_id not in self.player_sessions:
            return False
        
        session_id = self.player_sessions[user_id]
        if session_id not in self.active_games:
            return False
        
        game = self.active_games[session_id]
        
        # Удаляем пользователя из игры
        game.players = [p for p in game.players if p.user_id != user_id]
        del self.player_sessions[user_id]
        
        # Если в игре больше нет игроков, удаляем сессию
        if len(game.players) == 0:
            del self.active_games[session_id]
        
        return True
    
    async def end_game(self, session_id: str) -> bool:
        """Принудительное завершение игры"""
        if session_id not in self.active_games:
            return False
        
        game = self.active_games[session_id]
        
        # Удаляем всех игроков из сессий
        for player in game.players:
            if player.user_id in self.player_sessions:
                del self.player_sessions[player.user_id]
        
        # Удаляем игру
        del self.active_games[session_id]
        
        return True

# Глобальный экземпляр для использования в приложении
game_manager = GameManager(None, None)  # Будет инициализирован в основном приложении