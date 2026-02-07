"""
Enhanced test suite for the hybrid messenger application.

This module contains comprehensive tests covering:
- Unit tests for core components
- Integration tests for API endpoints
- Security tests for authentication and authorization
- Performance tests for message handling
- End-to-end tests for complete workflows
"""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import uuid
import hashlib
import base64

import aiohttp
from aiohttp import web, test_client
import asyncpg
import aioredis
from cryptography.fernet import Fernet

from app.main import init_app
from app.advanced_auth import AdvancedAuthManager
from app.advanced_encryption import AdvancedEncryptionManager
from app.performance_optimizations import QueryOptimizer, LRUCache
from app.type_definitions import User, Message, Chat, Task, CalendarEvent


class TestConfig:
    """Test configuration."""
    TEST_DB_URL = "postgresql://test:test@localhost:5432/test_messenger"
    TEST_REDIS_URL = "redis://localhost:6379/1"
    TEST_JWT_SECRET = "test-secret-key-for-testing"
    TEST_MESSAGE_ENCRYPTION_KEY = "test-message-encryption-key-for-testing"


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    """Create a test database pool."""
    pool = await asyncpg.create_pool(TestConfig.TEST_DB_URL, min_size=2, max_size=5)
    
    # Create test tables
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                last_seen TIMESTAMP DEFAULT NOW(),
                online_status VARCHAR(20) DEFAULT 'offline'
            );

            CREATE TABLE IF NOT EXISTS chats (
                id VARCHAR(100) PRIMARY KEY,
                type VARCHAR(20) NOT NULL,
                name VARCHAR(100),
                creator_id INTEGER REFERENCES users(id),
                participants INTEGER[],
                created_at TIMESTAMP DEFAULT NOW(),
                last_message TEXT,
                last_activity TIMESTAMP DEFAULT NOW(),
                unread_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id VARCHAR(100) REFERENCES chats(id),
                sender_id INTEGER REFERENCES users(id),
                content TEXT NOT NULL,
                message_type VARCHAR(20) DEFAULT 'text',
                timestamp TIMESTAMP DEFAULT NOW(),
                reply_to VARCHAR(50),
                edited BOOLEAN DEFAULT FALSE,
                edited_at TIMESTAMP,
                deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(100) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                assignee_id INTEGER REFERENCES users(id),
                creator_id INTEGER REFERENCES users(id),
                due_date TIMESTAMP,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'pending',
                task_type VARCHAR(20) DEFAULT 'personal',
                chat_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            );
        """)
    
    yield pool
    
    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await pool.close()


@pytest_asyncio.fixture(scope="session")
async def redis_client():
    """Create a test Redis client."""
    redis = aioredis.from_url(TestConfig.TEST_REDIS_URL, decode_responses=True)
    yield redis
    await redis.close()


@pytest_asyncio.fixture
async def app(db_pool, redis_client):
    """Create test application."""
    # Mock the global variables that would normally be set during startup
    import app.main
    app.main.db_pool = db_pool
    app.main.redis_client = redis_client
    
    application = await init_app()
    yield application


@pytest_asyncio.fixture
async def client(app):
    """Create test client."""
    async with test_client(app) as client:
        yield client


class TestAdvancedAuthManager:
    """Test cases for AdvancedAuthManager."""
    
    @pytest_asyncio.fixture
    async def auth_manager(self, db_pool, redis_client):
        """Create test auth manager."""
        encryption_manager = AdvancedEncryptionManager(TestConfig.TEST_MESSAGE_ENCRYPTION_KEY.encode())
        auth_manager = AdvancedAuthManager(db_pool, redis_client, encryption_manager)
        yield auth_manager
    
    async def test_password_hashing(self, auth_manager):
        """Test password hashing functionality."""
        password = "test_password_123"
        hashed = auth_manager.hash_password(password)
        
        assert hashed is not None
        assert len(hashed) > len(password)
        assert auth_manager.verify_password(password, hashed)
        assert not auth_manager.verify_password("wrong_password", hashed)
    
    async def test_token_creation_and_verification(self, auth_manager):
        """Test JWT token creation and verification."""
        user_data = {"sub": "test_user", "user_id": 123}
        token = auth_manager.create_access_token(user_data)
        
        assert token is not None
        
        verified_data = auth_manager.verify_token(token)
        assert verified_data is not None
        assert verified_data.username == "test_user"
    
    async def test_user_registration(self, auth_manager):
        """Test user registration with validation."""
        username = f"test_user_{uuid.uuid4().hex[:8]}"
        password = "SecurePassword123!"
        email = f"{username}@example.com"
        
        user = await auth_manager.register_user(username, password, email)
        
        assert user is not None
        assert user['username'] == username
        assert user['email'] == email
    
    async def test_user_authentication_success(self, auth_manager):
        """Test successful user authentication."""
        # First register a user
        username = f"auth_test_{uuid.uuid4().hex[:8]}"
        password = "SecurePassword123!"
        email = f"{username}@example.com"
        
        await auth_manager.register_user(username, password, email)
        
        # Then authenticate
        authenticated_user = await auth_manager.authenticate_user(username, password, "127.0.0.1")
        
        assert authenticated_user is not None
        assert authenticated_user['username'] == username
    
    async def test_user_authentication_failure(self, auth_manager):
        """Test failed user authentication."""
        username = f"fail_test_{uuid.uuid4().hex[:8]}"
        password = "SecurePassword123!"
        wrong_password = "WrongPassword456!"
        email = f"{username}@example.com"
        
        await auth_manager.register_user(username, password, email)
        
        # Try to authenticate with wrong password
        authenticated_user = await auth_manager.authenticate_user(username, wrong_password, "127.0.0.1")
        
        assert authenticated_user is None
    
    async def test_brute_force_protection(self, auth_manager):
        """Test brute force protection mechanism."""
        username = f"brute_test_{uuid.uuid4().hex[:8]}"
        password = "SecurePassword123!"
        email = f"{username}@example.com"
        
        await auth_manager.register_user(username, password, email)
        
        # Try to authenticate with wrong password multiple times
        for i in range(auth_manager.security_monitor.max_login_attempts):
            result = await auth_manager.authenticate_user(username, "wrong_password", "127.0.0.1")
            assert result is None
        
        # After max attempts, even correct password should fail due to lockout
        result = await auth_manager.authenticate_user(username, password, "127.0.0.1")
        assert result is None


class TestAdvancedEncryptionManager:
    """Test cases for AdvancedEncryptionManager."""
    
    @pytest_asyncio.fixture
    async def encryption_manager(self):
        """Create test encryption manager."""
        encryption_manager = AdvancedEncryptionManager(TestConfig.TEST_MESSAGE_ENCRYPTION_KEY.encode())
        yield encryption_manager
    
    async def test_aes_encryption_decryption(self, encryption_manager):
        """Test AES encryption and decryption."""
        original_message = "This is a secret message for testing encryption."
        
        # Encrypt
        encrypted_data = encryption_manager.encrypt_message(original_message)
        
        # Decrypt
        decrypted_message = encryption_manager.decrypt_message(encrypted_data)
        
        assert decrypted_message == original_message
    
    async def test_hybrid_encryption(self, encryption_manager):
        """Test hybrid encryption (AES + RSA)."""
        original_message = "Hybrid encryption test message."
        
        # Generate temporary RSA keys for testing
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        public_key = private_key.public_key()
        
        # Encrypt with hybrid method
        encrypted_package = encryption_manager.hybrid_encrypt(original_message, public_key)
        
        # Decrypt with hybrid method
        decrypted_message = encryption_manager.hybrid_decrypt(encrypted_package, private_key)
        
        assert decrypted_message == original_message
    
    async def test_message_integrity(self, encryption_manager):
        """Test that encrypted messages maintain integrity."""
        original_message = "Original message that should remain unchanged after encryption/decryption cycle."
        
        encrypted = encryption_manager.encrypt_message(original_message)
        decrypted = encryption_manager.decrypt_message(encrypted)
        
        assert decrypted == original_message
        assert len(encrypted) > len(original_message)  # Encrypted should be longer


class TestPerformanceOptimizations:
    """Test cases for performance optimizations."""
    
    @pytest_asyncio.fixture
    async def query_optimizer(self, db_pool):
        """Create test query optimizer."""
        query_optimizer = QueryOptimizer(db_pool)
        yield query_optimizer
    
    @pytest_asyncio.fixture
    async def lru_cache(self):
        """Create test LRU cache."""
        cache = LRUCache(max_size=100, ttl=300)  # 5 minute TTL
        yield cache
    
    async def test_lru_cache_basic_operations(self, lru_cache):
        """Test basic LRU cache operations."""
        # Test set and get
        lru_cache.set("key1", "value1")
        assert lru_cache.get("key1") == "value1"
        
        # Test non-existent key
        assert lru_cache.get("nonexistent") is None
        
        # Test cache size
        assert lru_cache.size() == 1
    
    async def test_lru_cache_eviction(self, lru_cache):
        """Test LRU cache eviction policy."""
        # Fill cache to max size
        for i in range(150):  # More than max size of 100
            lru_cache.set(f"key{i}", f"value{i}")
        
        # Cache should be at max size
        assert lru_cache.size() <= 100
        
        # Recently accessed items should still be in cache
        assert lru_cache.get("key149") == "value149"
    
    async def test_lru_cache_ttl(self, lru_cache):
        """Test LRU cache TTL functionality."""
        import time
        
        # Set item with short TTL
        lru_cache = LRUCache(max_size=10, ttl=1)  # 1 second TTL
        lru_cache.set("short_lived", "value")
        
        # Should be available immediately
        assert lru_cache.get("short_lived") == "value"
        
        # Wait for TTL to expire
        time.sleep(2)
        
        # Should be expired and removed
        assert lru_cache.get("short_lived") is None


class TestMessageHandling:
    """Test cases for message handling."""
    
    async def test_message_encryption_integration(self, app, client):
        """Test message encryption in the context of sending/receiving."""
        # Register a test user
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': f'test_user_{uuid.uuid4().hex[:8]}',
            'password': 'SecurePassword123!',
            'email': 'test@example.com'
        })
        assert register_resp.status == 200
        
        # Login
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': f'test_user_{uuid.uuid4().hex[:8]}',
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        
        login_data = await login_resp.json()
        token = login_data['access_token']
        
        # Create a test chat
        headers = {'Authorization': f'Bearer {token}'}
        chat_resp = await client.post('/api/v1/chats', json={
            'type': 'private',
            'name': 'Test Chat'
        }, headers=headers)
        assert chat_resp.status == 200
        
        chat_data = await chat_resp.json()
        chat_id = chat_data['id']
        
        # Send an encrypted message
        message_content = "This is a test message that should be encrypted."
        send_resp = await client.post(f'/api/v1/chats/{chat_id}/messages', json={
            'content': message_content,
            'encrypt_for_recipients': True
        }, headers=headers)
        assert send_resp.status == 200
        
        # Retrieve the message and verify it's properly handled
        history_resp = await client.get(f'/api/v1/chats/{chat_id}/messages', headers=headers)
        assert history_resp.status == 200
        
        history_data = await history_resp.json()
        assert len(history_data['messages']) > 0
        assert history_data['messages'][0]['content'] == message_content
    
    async def test_bulk_message_processing(self, app, client, db_pool):
        """Test bulk message processing performance."""
        # Register a test user
        username = f'bulk_test_{uuid.uuid4().hex[:8]}'
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': username,
            'password': 'SecurePassword123!',
            'email': 'bulk@example.com'
        })
        assert register_resp.status == 200
        
        # Login
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': username,
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        
        login_data = await login_resp.json()
        token = login_data['access_token']
        user_id = login_data['user']['id']
        
        # Create a test chat
        headers = {'Authorization': f'Bearer {token}'}
        chat_resp = await client.post('/api/v1/chats', json={
            'type': 'private',
            'name': 'Bulk Test Chat'
        }, headers=headers)
        assert chat_resp.status == 200
        
        chat_data = await chat_resp.json()
        chat_id = chat_data['id']
        
        # Measure time for sending multiple messages
        start_time = time.time()
        
        # Send 100 messages in quick succession
        for i in range(100):
            message_resp = await client.post(f'/api/v1/chats/{chat_id}/messages', json={
                'content': f'Test message #{i}',
                'message_type': 'text'
            }, headers=headers)
            assert message_resp.status == 200
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Processing 100 messages should take less than 10 seconds
        assert processing_time < 10.0, f"Bulk processing took too long: {processing_time}s"
        
        # Verify all messages were stored
        history_resp = await client.get(f'/api/v1/chats/{chat_id}/messages', headers=headers)
        assert history_resp.status == 200
        
        history_data = await history_resp.json()
        assert len(history_data['messages']) == 100


class TestSecurityFeatures:
    """Test cases for security features."""
    
    async def test_rate_limiting(self, app, client):
        """Test rate limiting functionality."""
        # Try to make many requests rapidly
        tasks = []
        for i in range(150):  # More than the rate limit
            task = client.post('/api/v1/auth/register', json={
                'username': f'rate_limit_test_{i}',
                'password': 'SecurePassword123!',
                'email': f'rate{i}@example.com'
            })
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful vs failed requests
        success_count = 0
        failure_count = 0
        
        for response in responses:
            if isinstance(response, Exception):
                failure_count += 1
            elif hasattr(response, 'status') and response.status in [200, 429]:  # 429 = rate limited
                if response.status == 429:
                    failure_count += 1
                else:
                    success_count += 1
        
        # At least some requests should be rate-limited
        assert failure_count > 0, "Rate limiting didn't work - all requests succeeded"
    
    async def test_sql_injection_protection(self, app, client):
        """Test protection against SQL injection."""
        # Register a user first
        username = f'sql_test_{uuid.uuid4().hex[:8]}'
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': username,
            'password': 'SecurePassword123!',
            'email': 'sql@example.com'
        })
        assert register_resp.status == 200
        
        # Try to login with potential SQL injection in username
        malicious_username = "admin'; DROP TABLE users; --"
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': malicious_username,
            'password': 'any_password'
        })
        
        # Should not crash and should return appropriate error
        assert login_resp.status in [401, 400], "SQL injection protection failed"
    
    async def test_xss_protection(self, app, client):
        """Test protection against XSS attacks."""
        # Register and login a user
        username = f'xss_test_{uuid.uuid4().hex[:8]}'
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': username,
            'password': 'SecurePassword123!',
            'email': 'xss@example.com'
        })
        assert register_resp.status == 200
        
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': username,
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        
        login_data = await login_resp.json()
        token = login_data['access_token']
        
        # Create a chat
        headers = {'Authorization': f'Bearer {token}'}
        chat_resp = await client.post('/api/v1/chats', json={
            'type': 'private',
            'name': 'XSS Test Chat'
        }, headers=headers)
        assert chat_resp.status == 200
        
        chat_data = await chat_resp.json()
        chat_id = chat_data['id']
        
        # Try to send a message with potential XSS
        malicious_message = '<script>alert("XSS Attack!")</script>'
        send_resp = await client.post(f'/api/v1/chats/{chat_id}/messages', json={
            'content': malicious_message,
            'message_type': 'text'
        }, headers=headers)
        assert send_resp.status == 200
        
        # Retrieve the message and verify it's sanitized
        history_resp = await client.get(f'/api/v1/chats/{chat_id}/messages', headers=headers)
        assert history_resp.status == 200
        
        history_data = await history_resp.json()
        retrieved_message = history_data['messages'][0]['content']
        
        # The XSS script should be sanitized/removed
        assert '<script>' not in retrieved_message.lower(), "XSS protection failed"


class TestWebSocketFunctionality:
    """Test cases for WebSocket functionality."""
    
    async def test_websocket_connection(self, app, aiohttp_client):
        """Test WebSocket connection establishment."""
        client = await aiohttp_client(app)
        
        # Establish WebSocket connection
        ws = await client.ws_connect('/ws')
        
        # Send authentication message
        auth_message = {
            'type': 'auth',
            'username': 'test_ws_user',
            'password': 'SecurePassword123!'
        }
        await ws.send_str(json.dumps(auth_message))
        
        # Receive response
        response = await ws.receive(timeout=5)
        assert response.type == aiohttp.WSMsgType.TEXT
        
        response_data = json.loads(response.data)
        # Note: This will fail because user doesn't exist, but connection should be established
        
        await ws.close()
    
    async def test_websocket_message_handling(self, app, aiohttp_client):
        """Test WebSocket message handling."""
        client = await aiohttp_client(app)
        
        # Establish WebSocket connection
        ws = await client.ws_connect('/ws')
        
        # First register and authenticate a user
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': f'ws_test_{uuid.uuid4().hex[:8]}',
            'password': 'SecurePassword123!',
            'email': 'ws@example.com'
        })
        assert register_resp.status == 200
        
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': f'ws_test_{uuid.uuid4().hex[:8]}',
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        
        login_data = await login_resp.json()
        token = login_data['access_token']
        
        # Send authentication via WebSocket
        auth_message = {
            'type': 'auth',
            'token': token
        }
        await ws.send_str(json.dumps(auth_message))
        
        # Receive auth confirmation
        auth_response = await ws.receive(timeout=5)
        assert auth_response.type == aiohttp.WSMsgType.TEXT
        
        # Send a test message
        test_message = {
            'type': 'message',
            'chat_id': 'general',
            'content': 'Test WebSocket message',
            'message_type': 'text'
        }
        await ws.send_str(json.dumps(test_message))
        
        # Receive message confirmation
        message_response = await ws.receive(timeout=5)
        assert message_response.type == aiohttp.WSMsgType.TEXT
        
        await ws.close()


class TestIntegration:
    """Integration tests for complete workflows."""
    
    async def test_complete_messaging_workflow(self, app, client):
        """Test complete messaging workflow: register -> login -> create chat -> send message -> receive."""
        # Step 1: Register user 1
        user1_username = f'user1_{uuid.uuid4().hex[:8]}'
        register_resp1 = await client.post('/api/v1/auth/register', json={
            'username': user1_username,
            'password': 'SecurePassword123!',
            'email': 'user1@example.com'
        })
        assert register_resp1.status == 200
        
        # Step 2: Register user 2
        user2_username = f'user2_{uuid.uuid4().hex[:8]}'
        register_resp2 = await client.post('/api/v1/auth/register', json={
            'username': user2_username,
            'password': 'SecurePassword123!',
            'email': 'user2@example.com'
        })
        assert register_resp2.status == 200
        
        # Step 3: Login user 1
        login_resp1 = await client.post('/api/v1/auth/login', json={
            'username': user1_username,
            'password': 'SecurePassword123!'
        })
        assert login_resp1.status == 200
        login_data1 = await login_resp1.json()
        token1 = login_data1['access_token']
        
        # Step 4: Login user 2
        login_resp2 = await client.post('/api/v1/auth/login', json={
            'username': user2_username,
            'password': 'SecurePassword123!'
        })
        assert login_resp2.status == 200
        login_data2 = await login_resp2.json()
        token2 = login_data2['access_token']
        
        # Step 5: Create private chat between users
        headers1 = {'Authorization': f'Bearer {token1}'}
        chat_resp = await client.post('/api/v1/chats', json={
            'type': 'private',
            'participants': [login_data1['user']['id'], login_data2['user']['id']]
        }, headers=headers1)
        assert chat_resp.status == 200
        chat_data = await chat_resp.json()
        chat_id = chat_data['id']
        
        # Step 6: User 1 sends message to user 2
        message_content = "Hello from user 1!"
        send_resp = await client.post(f'/api/v1/chats/{chat_id}/messages', json={
            'content': message_content,
            'message_type': 'text'
        }, headers=headers1)
        assert send_resp.status == 200
        
        # Step 7: User 2 retrieves messages
        headers2 = {'Authorization': f'Bearer {token2}'}
        history_resp = await client.get(f'/api/v1/chats/{chat_id}/messages', headers=headers2)
        assert history_resp.status == 200
        history_data = await history_resp.json()
        
        # Verify message was received correctly
        assert len(history_data['messages']) == 1
        assert history_data['messages'][0]['content'] == message_content
        assert history_data['messages'][0]['sender_id'] == login_data1['user']['id']
    
    async def test_task_management_integration(self, app, client):
        """Test task management integration."""
        # Register and login user
        username = f'task_test_{uuid.uuid4().hex[:8]}'
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': username,
            'password': 'SecurePassword123!',
            'email': 'task@example.com'
        })
        assert register_resp.status == 200
        
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': username,
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        login_data = await login_resp.json()
        token = login_data['access_token']
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Create a task
        task_resp = await client.post('/api/v1/tasks', json={
            'title': 'Test Task',
            'description': 'This is a test task',
            'assignee_id': login_data['user']['id'],
            'due_date': (datetime.utcnow() + timedelta(days=7)).isoformat(),
            'priority': 'high'
        }, headers=headers)
        assert task_resp.status == 200
        task_data = await task_resp.json()
        task_id = task_data['id']
        
        # Retrieve the task
        get_resp = await client.get(f'/api/v1/tasks/{task_id}', headers=headers)
        assert get_resp.status == 200
        retrieved_task = await get_resp.json()
        
        assert retrieved_task['title'] == 'Test Task'
        assert retrieved_task['description'] == 'This is a test task'
        assert retrieved_task['status'] == 'pending'
    
    async def test_calendar_integration(self, app, client):
        """Test calendar integration."""
        # Register and login user
        username = f'cal_test_{uuid.uuid4().hex[:8]}'
        register_resp = await client.post('/api/v1/auth/register', json={
            'username': username,
            'password': 'SecurePassword123!',
            'email': 'cal@example.com'
        })
        assert register_resp.status == 200
        
        login_resp = await client.post('/api/v1/auth/login', json={
            'username': username,
            'password': 'SecurePassword123!'
        })
        assert login_resp.status == 200
        login_data = await login_resp.json()
        token = login_data['access_token']
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Create a calendar event
        start_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        end_time = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        
        event_resp = await client.post('/api/v1/calendar/events', json={
            'title': 'Test Event',
            'description': 'This is a test event',
            'start_time': start_time,
            'end_time': end_time,
            'timezone': 'UTC',
            'privacy': 'private'
        }, headers=headers)
        assert event_resp.status == 200
        event_data = await event_resp.json()
        event_id = event_data['id']
        
        # Retrieve the event
        get_resp = await client.get(f'/api/v1/calendar/events/{event_id}', headers=headers)
        assert get_resp.status == 200
        retrieved_event = await get_resp.json()
        
        assert retrieved_event['title'] == 'Test Event'
        assert retrieved_event['description'] == 'This is a test event'
        assert retrieved_event['privacy'] == 'private'


class TestPerformance:
    """Performance tests."""
    
    async def test_concurrent_connections(self, app, aiohttp_client):
        """Test handling of concurrent connections."""
        num_clients = 50
        
        async def connect_and_auth(client_num):
            client = await aiohttp_client(app)
            
            # Register user
            username = f'perf_test_{uuid.uuid4().hex[:8]}_{client_num}'
            register_resp = await client.post('/api/v1/auth/register', json={
                'username': username,
                'password': 'SecurePassword123!',
                'email': f'{username}@example.com'
            })
            assert register_resp.status == 200
            
            # Login
            login_resp = await client.post('/api/v1/auth/login', json={
                'username': username,
                'password': 'SecurePassword123!'
            })
            assert login_resp.status == 200
            
            # Create chat and send message
            login_data = await login_resp.json()
            token = login_data['access_token']
            headers = {'Authorization': f'Bearer {token}'}
            
            chat_resp = await client.post('/api/v1/chats', json={
                'type': 'private',
                'name': f'Perf Chat {client_num}'
            }, headers=headers)
            assert chat_resp.status == 200
            
            chat_data = await chat_resp.json()
            chat_id = chat_data['id']
            
            send_resp = await client.post(f'/api/v1/chats/{chat_id}/messages', json={
                'content': f'Message from client {client_num}',
                'message_type': 'text'
            }, headers=headers)
            assert send_resp.status == 200
            
            await client.close()
        
        # Run all clients concurrently
        start_time = time.time()
        await asyncio.gather(*[connect_and_auth(i) for i in range(num_clients)])
        end_time = time.time()
        
        total_time = end_time - start_time
        
        # All 50 clients should complete within 30 seconds
        assert total_time < 30.0, f"All concurrent operations took too long: {total_time}s"
    
    async def test_database_performance(self, db_pool):
        """Test database performance with bulk operations."""
        # Insert many users
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            # Use bulk insert
            values = []
            for i in range(1000):
                username = f'bulk_user_{i}_{uuid.uuid4().hex[:8]}'
                password_hash = '$2b$12$LQv3c1y4Jx7Nz9Y2v6x8euOFEG9l6J3nR5z8v7Y4Jx7Nz9Y2v6x8e'  # bcrypt hash of 'password'
                values.append((username, password_hash, f'{username}@example.com'))
            
            await conn.executemany(
                "INSERT INTO users (username, password_hash, email) VALUES ($1, $2, $3)",
                values
            )
        
        end_time = time.time()
        insertion_time = end_time - start_time
        
        # 1000 users should be inserted in under 5 seconds
        assert insertion_time < 5.0, f"Bulk insertion took too long: {insertion_time}s"
        
        # Test bulk retrieval
        start_time = time.time()
        async with db_pool.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users LIMIT 1000")
        
        end_time = time.time()
        retrieval_time = end_time - start_time
        
        # Retrieving 1000 users should take under 2 seconds
        assert retrieval_time < 2.0, f"Bulk retrieval took too long: {retrieval_time}s"
        assert len(users) == 1000


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])