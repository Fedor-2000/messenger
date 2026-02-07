# server/app/technical_improvements.py
import asyncio
import aioredis
import asyncpg
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import time
import traceback
import sys
import os
from contextlib import asynccontextmanager
import weakref
import gc
import threading
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import inspect
import types
from functools import wraps, partial
import cProfile
import pstats
from io import StringIO
import psutil
import tracemalloc
from pathlib import Path
import importlib.util
import pkg_resources
import platform
import resource

logger = logging.getLogger(__name__)

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    disk_usage: float
    network_io: Dict[str, int]
    process_count: int
    uptime: float
    timestamp: float

@dataclass
class PerformanceMetrics:
    request_count: int
    error_count: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    active_connections: int
    memory_usage: float
    cpu_usage: float
    timestamp: float

class AdvancedLogger:
    """Улучшенный логгер с поддержкой структурированных логов"""
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.value))
        
        # Создаем форматтер для структурированных логов
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(module)s", '
            '"function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}'
        )
        
        # Удаляем существующие хендлеры
        self.logger.handlers.clear()
        
        # Добавляем хендлер для файла
        file_handler = logging.FileHandler('messenger.log')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Добавляем хендлер для консоли
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Добавляем хендлер для ротации логов
        from logging.handlers import RotatingFileHandler
        rotating_handler = RotatingFileHandler(
            'messenger.log', 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        rotating_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_handler)
    
    def debug(self, message: str, extra: Optional[Dict] = None):
        self.logger.debug(message, extra=extra or {})
    
    def info(self, message: str, extra: Optional[Dict] = None):
        self.logger.info(message, extra=extra or {})
    
    def warning(self, message: str, extra: Optional[Dict] = None):
        self.logger.warning(message, extra=extra or {})
    
    def error(self, message: str, extra: Optional[Dict] = None):
        self.logger.error(message, extra=extra or {})
    
    def critical(self, message: str, extra: Optional[Dict] = None):
        self.logger.critical(message, extra=extra or {})

class MemoryManager:
    """Менеджер управления памятью"""
    
    def __init__(self):
        self.objects = weakref.WeakSet()
        self.object_counts = {}
        self.max_memory_usage = 512 * 1024 * 1024  # 512 MB
        self.gc_threshold = 0.8  # 80% от max_memory_usage
    
    def track_object(self, obj):
        """Отслеживание объекта"""
        self.objects.add(obj)
        obj_type = type(obj).__name__
        self.object_counts[obj_type] = self.object_counts.get(obj_type, 0) + 1
    
    def get_memory_usage(self) -> float:
        """Получение текущего использования памяти"""
        process = psutil.Process()
        return process.memory_info().rss
    
    def get_memory_percentage(self) -> float:
        """Получение процента использования памяти"""
        total_memory = psutil.virtual_memory().total
        used_memory = self.get_memory_usage()
        return (used_memory / total_memory) * 100
    
    def cleanup(self):
        """Очистка памяти"""
        # Принудительная сборка мусора
        collected = gc.collect()
        logger.info(f"Garbage collection completed. Collected {collected} objects")
        
        # Проверка использования памяти
        if self.get_memory_usage() > self.max_memory_usage * self.gc_threshold:
            # Дополнительная очистка
            self.force_cleanup()
    
    def force_cleanup(self):
        """Принудительная очистка"""
        # Очистка кэшей
        import sys
        if hasattr(sys, '_clear_type_cache'):
            sys._clear_type_cache()
        
        # Очистка слабых ссылок
        for obj in list(self.objects):
            if obj is None:
                self.objects.discard(obj)

class PerformanceProfiler:
    """Профайлер производительности"""
    
    def __init__(self):
        self.profiles = {}
        self.metrics = {}
        self.tracing_enabled = False
    
    def start_tracing(self):
        """Начать трассировку"""
        tracemalloc.start()
        self.tracing_enabled = True
    
    def stop_tracing(self):
        """Остановить трассировку"""
        if self.tracing_enabled:
            tracemalloc.stop()
            self.tracing_enabled = False
    
    def profile_function(self, func: Callable) -> Callable:
        """Декоратор для профилирования функции"""
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = tracemalloc.take_snapshot() if self.tracing_enabled else None
            
            try:
                result = await func(*args, **kwargs)
                success = True
            except Exception as e:
                success = False
                raise
            finally:
                end_time = time.time()
                end_memory = tracemalloc.take_snapshot() if self.tracing_enabled else None
                
                # Сбор метрик
                duration = end_time - start_time
                memory_diff = 0
                if start_memory and end_memory:
                    memory_diff = end_memory.compare_to(start_memory, 'lineno')[0].size_diff
                
                func_name = f"{func.__module__}.{func.__name__}"
                if func_name not in self.metrics:
                    self.metrics[func_name] = {
                        'call_count': 0,
                        'total_time': 0,
                        'avg_time': 0,
                        'min_time': float('inf'),
                        'max_time': 0,
                        'total_memory_diff': 0,
                        'success_count': 0,
                        'error_count': 0
                    }
                
                metrics = self.metrics[func_name]
                metrics['call_count'] += 1
                metrics['total_time'] += duration
                metrics['avg_time'] = metrics['total_time'] / metrics['call_count']
                metrics['min_time'] = min(metrics['min_time'], duration)
                metrics['max_time'] = max(metrics['max_time'], duration)
                metrics['total_memory_diff'] += memory_diff
                if success:
                    metrics['success_count'] += 1
                else:
                    metrics['error_count'] += 1
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            start_memory = tracemalloc.take_snapshot() if self.tracing_enabled else None
            
            try:
                result = func(*args, **kwargs)
                success = True
            except Exception as e:
                success = False
                raise
            finally:
                end_time = time.time()
                end_memory = tracemalloc.take_snapshot() if self.tracing_enabled else None
                
                # Сбор метрик
                duration = end_time - start_time
                memory_diff = 0
                if start_memory and end_memory:
                    memory_diff = end_memory.compare_to(start_memory, 'lineno')[0].size_diff
                
                func_name = f"{func.__module__}.{func.__name__}"
                if func_name not in self.metrics:
                    self.metrics[func_name] = {
                        'call_count': 0,
                        'total_time': 0,
                        'avg_time': 0,
                        'min_time': float('inf'),
                        'max_time': 0,
                        'total_memory_diff': 0,
                        'success_count': 0,
                        'error_count': 0
                    }
                
                metrics = self.metrics[func_name]
                metrics['call_count'] += 1
                metrics['total_time'] += duration
                metrics['avg_time'] = metrics['total_time'] / metrics['call_count']
                metrics['min_time'] = min(metrics['min_time'], duration)
                metrics['max_time'] = max(metrics['max_time'], duration)
                metrics['total_memory_diff'] += memory_diff
                if success:
                    metrics['success_count'] += 1
                else:
                    metrics['error_count'] += 1
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    def get_profile_stats(self) -> Dict[str, Any]:
        """Получение статистики профилирования"""
        return {
            'functions': self.metrics,
            'total_calls': sum(m['call_count'] for m in self.metrics.values()),
            'total_errors': sum(m['error_count'] for m in self.metrics.values()),
            'overall_avg_time': sum(m['total_time'] for m in self.metrics.values()) / 
                              max(sum(m['call_count'] for m in self.metrics.values()), 1)
        }

class ErrorManager:
    """Менеджер обработки ошибок"""
    
    def __init__(self):
        self.error_handlers = {}
        self.error_log = []
        self.max_error_log_size = 1000
        self.error_callbacks = []
    
    def register_error_handler(self, exception_type: type, handler: Callable):
        """Регистрация обработчика ошибок"""
        self.error_handlers[exception_type] = handler
    
    def add_error_callback(self, callback: Callable):
        """Добавление callback для обработки ошибок"""
        self.error_callbacks.append(callback)
    
    def handle_error(self, error: Exception, context: Optional[Dict] = None):
        """Обработка ошибки"""
        error_info = {
            'error': str(error),
            'type': type(error).__name__,
            'traceback': traceback.format_exc(),
            'context': context or {},
            'timestamp': time.time()
        }
        
        # Добавляем в лог
        self.error_log.append(error_info)
        if len(self.error_log) > self.max_error_log_size:
            self.error_log.pop(0)
        
        # Вызываем зарегистрированные обработчики
        for exc_type, handler in self.error_handlers.items():
            if isinstance(error, exc_type):
                try:
                    handler(error, context)
                except Exception as handler_error:
                    logger.error(f"Error in error handler: {handler_error}")
        
        # Вызываем callbacks
        for callback in self.error_callbacks:
            try:
                callback(error_info)
            except Exception as callback_error:
                logger.error(f"Error in error callback: {callback_error}")
        
        # Логируем ошибку
        logger.error(f"Error occurred: {error_info['type']}: {error_info['error']}", 
                    extra={'context': context})
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Получение статистики ошибок"""
        if not self.error_log:
            return {'total_errors': 0, 'error_types': {}, 'recent_errors': []}
        
        error_types = {}
        for error in self.error_log:
            error_type = error['type']
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            'total_errors': len(self.error_log),
            'error_types': error_types,
            'recent_errors': self.error_log[-10:]  # последние 10 ошибок
        }

class DependencyManager:
    """Менеджер зависимостей"""
    
    def __init__(self):
        self.dependencies = {}
        self.optional_dependencies = {}
        self.installed_packages = set()
        self.check_dependencies()
    
    def check_dependencies(self):
        """Проверка установленных зависимостей"""
        try:
            for dist in pkg_resources.working_set:
                self.installed_packages.add(dist.project_name.lower())
        except Exception as e:
            logger.error(f"Error checking dependencies: {e}")
    
    def register_dependency(self, name: str, version: str, optional: bool = False):
        """Регистрация зависимости"""
        dep_info = {'name': name, 'version': version, 'installed': name.lower() in self.installed_packages}
        
        if optional:
            self.optional_dependencies[name] = dep_info
        else:
            self.dependencies[name] = dep_info
    
    def check_requirement(self, package_name: str, version: str = None) -> bool:
        """Проверка требования зависимости"""
        try:
            pkg_resources.require(f"{package_name}{version or ''}")
            return True
        except pkg_resources.DistributionNotFound:
            return False
        except pkg_resources.VersionConflict:
            return False
    
    def get_missing_dependencies(self) -> List[str]:
        """Получение списка отсутствующих зависимостей"""
        missing = []
        for name, info in self.dependencies.items():
            if not info['installed']:
                missing.append(name)
        return missing
    
    def get_optional_features_status(self) -> Dict[str, bool]:
        """Получение статуса опциональных возможностей"""
        status = {}
        for name, info in self.optional_dependencies.items():
            status[name] = info['installed']
        return status

class ConfigurationValidator:
    """Валидатор конфигурации"""
    
    def __init__(self):
        self.validators = {}
        self.required_configs = set()
        self.config_types = {}
    
    def register_validator(self, config_name: str, validator: Callable, required: bool = True, config_type: type = str):
        """Регистрация валидатора конфигурации"""
        self.validators[config_name] = validator
        self.config_types[config_name] = config_type
        if required:
            self.required_configs.add(config_name)
    
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, List[str]]:
        """Валидация конфигурации"""
        errors = {}
        
        # Проверка обязательных параметров
        for required in self.required_configs:
            if required not in config:
                if required not in errors:
                    errors[required] = []
                errors[required].append(f"Required configuration parameter '{required}' is missing")
        
        # Валидация значений
        for config_name, value in config.items():
            if config_name in self.validators:
                try:
                    is_valid, error_msg = self.validators[config_name](value)
                    if not is_valid:
                        if config_name not in errors:
                            errors[config_name] = []
                        errors[config_name].append(error_msg)
                except Exception as e:
                    if config_name not in errors:
                        errors[config_name] = []
                    errors[config_name].append(f"Validation error: {str(e)}")
        
        return errors
    
    def add_string_validator(self, config_name: str, min_length: int = 1, max_length: int = None, 
                           allowed_chars: str = None, required: bool = True):
        """Добавление валидатора строк"""
        def validator(value):
            if not isinstance(value, str):
                return False, f"Expected string, got {type(value).__name__}"
            
            if len(value) < min_length:
                return False, f"String too short, minimum length is {min_length}"
            
            if max_length and len(value) > max_length:
                return False, f"String too long, maximum length is {max_length}"
            
            if allowed_chars and not all(c in allowed_chars for c in value):
                return False, f"String contains disallowed characters"
            
            return True, ""
        
        self.register_validator(config_name, validator, required, str)
    
    def add_int_validator(self, config_name: str, min_value: int = None, max_value: int = None, required: bool = True):
        """Добавление валидатора целых чисел"""
        def validator(value):
            if not isinstance(value, int):
                return False, f"Expected integer, got {type(value).__name__}"
            
            if min_value is not None and value < min_value:
                return False, f"Value too small, minimum is {min_value}"
            
            if max_value is not None and value > max_value:
                return False, f"Value too large, maximum is {max_value}"
            
            return True, ""
        
        self.register_validator(config_name, validator, required, int)
    
    def add_bool_validator(self, config_name: str, required: bool = True):
        """Добавление валидатора булевых значений"""
        def validator(value):
            if not isinstance(value, bool):
                return False, f"Expected boolean, got {type(value).__name__}"
            return True, ""
        
        self.register_validator(config_name, validator, required, bool)

class SystemMonitor:
    """Системный монитор"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_time = time.time()
        self.metrics_history = []
        self.max_history_size = 100
    
    def get_system_metrics(self) -> SystemMetrics:
        """Получение метрик системы"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
        net_io = psutil.net_io_counters()
        process_count = len(psutil.pids())
        uptime = time.time() - self.start_time
        
        network_io = {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        }
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_usage=disk_usage,
            network_io=network_io,
            process_count=process_count,
            uptime=uptime,
            timestamp=time.time()
        )
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        """Получение метрик производительности приложения"""
        # Эти значения должны обновляться в реальном времени
        # В реальном приложении они будут собираться из других компонентов
        return PerformanceMetrics(
            request_count=getattr(self, 'request_count', 0),
            error_count=getattr(self, 'error_count', 0),
            avg_response_time=getattr(self, 'avg_response_time', 0),
            p95_response_time=getattr(self, 'p95_response_time', 0),
            p99_response_time=getattr(self, 'p99_response_time', 0),
            active_connections=getattr(self, 'active_connections', 0),
            memory_usage=self.process.memory_info().rss / 1024 / 1024,  # MB
            cpu_usage=self.process.cpu_percent(),
            timestamp=time.time()
        )
    
    def collect_metrics(self):
        """Сбор метрик"""
        metrics = self.get_system_metrics()
        self.metrics_history.append(metrics)
        
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history.pop(0)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Получение сводки метрик"""
        if not self.metrics_history:
            return {}
        
        cpu_values = [m.cpu_percent for m in self.metrics_history]
        memory_values = [m.memory_percent for m in self.metrics_history]
        
        return {
            'cpu_avg': sum(cpu_values) / len(cpu_values),
            'cpu_peak': max(cpu_values),
            'memory_avg': sum(memory_values) / len(memory_values),
            'memory_peak': max(memory_values),
            'total_collected': len(self.metrics_history),
            'time_range': {
                'start': self.metrics_history[0].timestamp,
                'end': self.metrics_history[-1].timestamp
            }
        }

class AsyncResourceManager:
    """Менеджер асинхронных ресурсов"""
    
    def __init__(self):
        self.resources = {}
        self.cleanup_callbacks = []
        self.resource_locks = {}
    
    async def acquire_resource(self, resource_name: str, factory: Callable, *args, **kwargs):
        """Получение ресурса"""
        if resource_name not in self.resources:
            # Создаем ресурс
            resource = await factory(*args, **kwargs) if asyncio.iscoroutinefunction(factory) else factory(*args, **kwargs)
            self.resources[resource_name] = resource
            
            # Регистрируем callback для очистки
            if hasattr(resource, 'close') or hasattr(resource, 'aclose'):
                self.cleanup_callbacks.append(partial(self._cleanup_resource, resource_name))
        
        return self.resources[resource_name]
    
    async def _cleanup_resource(self, resource_name: str):
        """Очистка ресурса"""
        if resource_name in self.resources:
            resource = self.resources[resource_name]
            try:
                if hasattr(resource, 'close'):
                    resource.close()
                elif hasattr(resource, 'aclose'):
                    await resource.aclose()
            except Exception as e:
                logger.error(f"Error closing resource {resource_name}: {e}")
            finally:
                del self.resources[resource_name]
    
    async def cleanup_all(self):
        """Очистка всех ресурсов"""
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback.func if hasattr(callback, 'func') else callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in cleanup callback: {e}")
        
        self.resources.clear()
        self.cleanup_callbacks.clear()

class CodeAnalyzer:
    """Анализатор кода"""
    
    @staticmethod
    def analyze_complexity(func: Callable) -> Dict[str, Any]:
        """Анализ сложности функции"""
        source = inspect.getsource(func)
        lines = source.split('\n')
        
        # Подсчет сложности (упрощенный вариант)
        complexity = 1  # базовая сложность
        for line in lines:
            line = line.strip()
            if any(keyword in line for keyword in ['if ', 'elif ', 'else:', 'for ', 'while ', 'except:']):
                complexity += 1
        
        # Подсчет строк кода
        code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('#'))
        
        return {
            'cyclomatic_complexity': complexity,
            'lines_of_code': code_lines,
            'function_name': func.__name__,
            'module': func.__module__
        }
    
    @staticmethod
    def find_async_patterns(code: str) -> List[Dict[str, Any]]:
        """Поиск асинхронных паттернов в коде"""
        patterns = []
        
        # Поиск async функций
        import ast
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    patterns.append({
                        'type': 'async_function',
                        'name': node.name,
                        'line': node.lineno
                    })
                elif isinstance(node, ast.Await):
                    patterns.append({
                        'type': 'await_expression',
                        'line': node.lineno
                    })
        except SyntaxError:
            import logging
            logging.warning(f"Syntax error in code pattern analysis")
        
        return patterns

class SecurityAuditor:
    """Аудит безопасности"""
    
    def __init__(self):
        self.security_issues = []
        self.audit_rules = []
    
    def add_audit_rule(self, rule_func: Callable, description: str):
        """Добавление правила аудита"""
        self.audit_rules.append({
            'rule': rule_func,
            'description': description
        })
    
    def audit_code(self, code: str) -> List[Dict[str, Any]]:
        """Аудит кода на предмет уязвимостей"""
        issues = []
        
        # Проверка на потенциальные уязвимости
        if 'eval(' in code or 'exec(' in code:
            issues.append({
                'type': 'code_execution',
                'description': 'Potential code execution vulnerability found',
                'severity': 'HIGH'
            })
        
        if 'os.system(' in code or 'subprocess.' in code:
            issues.append({
                'type': 'command_injection',
                'description': 'Potential command injection vulnerability found',
                'severity': 'HIGH'
            })
        
        if 'password' in code.lower() and '=' in code:
            issues.append({
                'type': 'hardcoded_credentials',
                'description': 'Potential hardcoded credentials found',
                'severity': 'MEDIUM'
            })
        
        # Применение пользовательских правил
        for rule_info in self.audit_rules:
            try:
                rule_issues = rule_info['rule'](code)
                issues.extend(rule_issues)
            except Exception as e:
                logger.error(f"Error in security audit rule: {e}")
        
        return issues
    
    def generate_security_report(self) -> str:
        """Генерация отчета безопасности"""
        report = "Security Audit Report\n"
        report += "=" * 50 + "\n\n"
        
        if not self.security_issues:
            report += "No security issues found.\n"
        else:
            report += f"Found {len(self.security_issues)} security issues:\n\n"
            for i, issue in enumerate(self.security_issues, 1):
                report += f"{i}. {issue['type']}\n"
                report += f"   Description: {issue['description']}\n"
                report += f"   Severity: {issue['severity']}\n\n"
        
        return report

# Глобальные экземпляры
advanced_logger = AdvancedLogger('messenger')
memory_manager = MemoryManager()
performance_profiler = PerformanceProfiler()
error_manager = ErrorManager()
dependency_manager = DependencyManager()
config_validator = ConfigurationValidator()
system_monitor = SystemMonitor()
async_resource_manager = AsyncResourceManager()
code_analyzer = CodeAnalyzer()
security_auditor = SecurityAuditor()

# Инициализация валидаторов конфигурации
config_validator.add_string_validator('JWT_SECRET', min_length=32)
config_validator.add_string_validator('MESSAGE_ENCRYPTION_KEY', min_length=32)
config_validator.add_int_validator('TCP_PORT', min_value=1, max_value=65535)
config_validator.add_int_validator('HTTP_PORT', min_value=1, max_value=65535)
config_validator.add_bool_validator('DEBUG_MODE')

# Регистрация обработчиков ошибок
def default_error_handler(error: Exception, context: Optional[Dict]):
    """Обработчик необработанных ошибок с полной логикой"""
    import traceback
    from datetime import datetime

    # Логируем подробную информацию об ошибке
    error_details = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'error_traceback': traceback.format_exc(),
        'context': context or {},
        'timestamp': datetime.utcnow().isoformat(),
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
    }

    logger.error(f"Unhandled error: {error}", extra=error_details)

    # Сохраняем ошибку в базу данных для дальнейшего анализа
    async def save_error_to_db():
        try:
            # Используем глобальный пул подключений, если он доступен
            if 'db_pool' in globals():
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO error_logs (error_type, error_message, traceback, context, timestamp)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        error_details['error_type'],
                        error_details['error_message'],
                        error_details['error_traceback'],
                        json.dumps(error_details['context']),
                        error_details['timestamp']
                    )
        except Exception as db_error:
            logger.error(f"Failed to save error to database: {db_error}")

    # Запускаем сохранение ошибки в фоне
    if 'asyncio' in globals():
        asyncio.create_task(save_error_to_db())

    # Отправляем уведомление администратору (если это критическая ошибка)
    if isinstance(error, (SystemError, OSError, MemoryError)):
        async def notify_admin():
            try:
                # Используем глобальный менеджер уведомлений, если он доступен
                if 'notification_service' in globals():
                    await notification_service.send_notification(
                        user_id=1,  # ID администратора
                        title="Критическая ошибка в системе",
                        body=f"Произошла критическая ошибка: {error_details['error_type']}: {error_details['error_message']}",
                        notification_type="critical_error"
                    )
            except Exception as notify_error:
                logger.error(f"Failed to notify admin about error: {notify_error}")

        if 'asyncio' in globals():
            asyncio.create_task(notify_admin())

error_manager.register_error_handler(Exception, default_error_handler)