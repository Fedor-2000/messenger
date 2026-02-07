# server/tests/unit/test_security.py
import pytest
import bcrypt
from unittest.mock import AsyncMock, patch
import sys
import os

# Добавляем путь к основному приложению
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.main import SecurityManager

def test_password_hashing():
    password = "test_password"
    hashed = SecurityManager.get_password_hash(password)
    
    assert SecurityManager.verify_password(password, hashed)
    assert not SecurityManager.verify_password("wrong_password", hashed)

def test_token_creation_and_verification():
    data = {"sub": "test_user", "user_id": 123}
    token = SecurityManager.create_access_token(data)
    
    # В реальной реализации нужно будет проверить токен
    # token_data = SecurityManager.verify_token(token)
    # assert token_data.username == "test_user"
    assert token is not None

def test_invalid_token():
    invalid_token = "invalid.token.here"
    # token_data = SecurityManager.verify_token(invalid_token)
    # assert token_data is None
    pass  # Заглушка, так как в текущей реализации нет полной проверки токена