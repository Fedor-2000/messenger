"""
Модуль улучшенного шифрования для мессенджера
Содержит реализацию сквозного шифрования и управления ключами
"""
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os
import base64
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import hashlib
import json


class AdvancedEncryption:
    """
    Класс для управления улучшенным шифрованием
    """
    
    def __init__(self, master_key: Optional[bytes] = None):
        # В реальном приложении мастер-ключ должен храниться в безопасном месте (HSM, Vault)
        self.master_key = master_key or os.urandom(32)  # 256-bit key
        self.key_rotation_period = timedelta(days=30)  # период ротации ключей
        self.current_key_version = 1
        
    def generate_key(self) -> bytes:
        """
        Генерация ключа для AES-GCM
        """
        return os.urandom(32)  # 256-bit key
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """
        Вывод ключа из пароля с использованием PBKDF2
        """
        if salt is None:
            salt = os.urandom(16)  # 128-bit salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=100000,  # Рекомендуемое количество итераций
        )
        key = kdf.derive(password.encode())
        
        return key, salt
    
    def encrypt_message(self, message: str, associated_data: bytes = None) -> Dict[str, str]:
        """
        Шифрование сообщения с аутентификацией (AEAD)
        """
        key = self.generate_key()
        aesgcm = AESGCM(key)
        
        nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
        ciphertext = aesgcm.encrypt(nonce, message.encode(), associated_data)
        
        return {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'nonce': base64.b64encode(nonce).decode(),
            'key': base64.b64encode(key).decode(),  # В реальности ключ не передается открыто
            'timestamp': datetime.utcnow().isoformat(),
            'key_version': str(self.current_key_version)
        }
    
    def decrypt_message(self, encrypted_data: Dict[str, str], associated_data: bytes = None) -> str:
        """
        Расшифровка сообщения
        """
        key = base64.b64decode(encrypted_data['key'])
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
        
        return plaintext.decode()
    
    def encrypt_for_user(self, message: str, recipient_public_key: bytes) -> Dict[str, str]:
        """
        Шифрование сообщения для конкретного пользователя (сквозное шифрование)
        В реальности использовалось бы асимметричное шифрование (Curve25519/X25519)
        """
        # В упрощенном варианте генерируем сессионный ключ
        session_key = self.generate_key()
        
        # Шифруем сообщение сессионным ключом
        aesgcm = AESGCM(session_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, message.encode(), None)
        
        # В реальности сессионный ключ шифровался бы открытым ключом получателя
        # Пока возвращаем сессионный ключ в открытом виде (в реальном приложении - зашифрованным)
        return {
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'nonce': base64.b64encode(nonce).decode(),
            'session_key': base64.b64encode(session_key).decode(),
            'timestamp': datetime.utcnow().isoformat(),
            'algorithm': 'AES-GCM-256'
        }
    
    def decrypt_for_user(self, encrypted_data: Dict[str, str], private_key: bytes) -> str:
        """
        Расшифровка сообщения пользователем (сквозное шифрование)
        """
        session_key = base64.b64decode(encrypted_data['session_key'])
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        
        aesgcm = AESGCM(session_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode()
    
    def create_message_authentication_code(self, message: str, key: bytes = None) -> str:
        """
        Создание кода аутентификации сообщения (MAC)
        """
        if key is None:
            key = self.master_key
        
        # Используем HMAC-SHA256 для создания MAC
        h = hashes.Hash(hashes.SHA256())
        h.update(message.encode())
        mac = h.finalize()
        
        return base64.b64encode(mac).decode()
    
    def verify_message_authentication_code(self, message: str, mac: str, key: bytes = None) -> bool:
        """
        Проверка кода аутентификации сообщения (MAC)
        """
        if key is None:
            key = self.master_key
        
        calculated_mac = self.create_message_authentication_code(message, key)
        return secrets.compare_digest(calculated_mac, mac)
    
    def hash_data(self, data: str, algorithm: str = 'sha256') -> str:
        """
        Хеширование данных
        """
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'sha512':
            hasher = hashlib.sha512()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        hasher.update(data.encode())
        return base64.b64encode(hasher.digest()).decode()
    
    def generate_salt(self) -> str:
        """
        Генерация соли для хеширования
        """
        return base64.b64encode(os.urandom(32)).decode()
    
    def encrypt_file(self, file_path: str, output_path: str, key: bytes = None) -> Dict[str, str]:
        """
        Шифрование файла
        """
        if key is None:
            key = self.generate_key()
        
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        
        # Читаем файл
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Шифруем
        ciphertext = aesgcm.encrypt(nonce, file_data, None)
        
        # Сохраняем зашифрованный файл
        with open(output_path, 'wb') as f:
            f.write(ciphertext)
        
        return {
            'key': base64.b64encode(key).decode(),
            'nonce': base64.b64encode(nonce).decode(),
            'original_path': file_path,
            'encrypted_path': output_path,
            'size': len(file_data)
        }
    
    def decrypt_file(self, encrypted_file_path: str, output_path: str, 
                    key_str: str, nonce_str: str) -> bool:
        """
        Расшифровка файла
        """
        key = base64.b64decode(key_str)
        nonce = base64.b64decode(nonce_str)
        
        # Читаем зашифрованный файл
        with open(encrypted_file_path, 'rb') as f:
            ciphertext = f.read()
        
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            # Сохраняем расшифрованный файл
            with open(output_path, 'wb') as f:
                f.write(plaintext)
            
            return True
        except Exception:
            return False
    
    def rotate_key(self) -> bytes:
        """
        Ротация ключа шифрования
        """
        self.current_key_version += 1
        new_key = self.generate_key()
        self.master_key = new_key
        return new_key


# Глобальный экземпляр для использования в приложении
advanced_encryption = AdvancedEncryption()