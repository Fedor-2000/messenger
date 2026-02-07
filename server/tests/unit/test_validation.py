# server/tests/unit/test_validation.py
import pytest
from pydantic import ValidationError
import sys
import os

# Добавляем путь к основному приложению
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.main import MessageEncryption, RateLimiter

def test_message_encryption():
    encryption = MessageEncryption()
    original_message = "Hello, this is a secret message!"
    
    encrypted = encryption.encrypt_message(original_message)
    decrypted = encryption.decrypt_message(encrypted)
    
    assert decrypted == original_message

def test_rate_limiter():
    limiter = RateLimiter(max_requests=3, time_window=10)  # 3 запроса за 10 секунд
    
    client_id = "test_client"
    
    # Первые 3 запроса должны быть разрешены
    assert limiter.is_allowed(client_id)
    assert limiter.is_allowed(client_id)
    assert limiter.is_allowed(client_id)
    
    # 4-й запрос должен быть ограничен
    assert not limiter.is_allowed(client_id)