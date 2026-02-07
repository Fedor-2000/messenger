# server/tests/integration/test_api.py
import pytest
import pytest_asyncio
import asyncio
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
import json
import sys
import os

# Добавляем путь к основному приложению
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.main import init_app

@pytest_asyncio.fixture
async def app():
    app_instance = await init_app()
    return app_instance

async def test_websocket_connection(aiohttp_client, app):
    client = await aiohttp_client(app)

    # Тестируем WebSocket подключение
    ws = await client.ws_connect('/ws')

    # Отправляем сообщение аутентификации
    auth_message = {
        'type': 'auth',
        'username': 'test_user',
        'password': 'test_password'
    }
    await ws.send_str(json.dumps(auth_message))

    # Ждем ответ
    response = await ws.receive()
    assert response.type == web.WSMsgType.TEXT

    # Закрываем соединение
    await ws.close()

async def test_rest_api_login(aiohttp_client, app):
    client = await aiohttp_client(app)

    # Тестируем REST API
    login_data = {
        'username': 'test_user',
        'password': 'test_password'
    }

    resp = await client.post('/api/login', json=login_data)
    assert resp.status == 200

    json_response = await resp.json()
    assert 'success' in json_response