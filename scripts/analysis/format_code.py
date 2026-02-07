# scripts/analysis/format_code.py
#!/usr/bin/env python3
"""
Скрипт для автоматического форматирования кода.
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse

def run_command(cmd):
    """Выполнение команды и возврат результата."""
    print(f"Запуск: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0

def format_with_black():
    """Форматирование с помощью black."""
    print("Форматирование с помощью black...")
    return run_command([
        "python", "-m", "black", "--config", "pyproject.toml", "server/"
    ])

def sort_imports():
    """Сортировка импортов с помощью isort."""
    print("Сортировка импортов с помощью isort...")
    return run_command([
        "python", "-m", "isort", "--settings-path", "pyproject.toml", "server/"
    ])

def check_types():
    """Проверка типов с помощью mypy."""
    print("Проверка типов с помощью mypy...")
    return run_command([
        "python", "-m", "mypy", "--config-file", "mypy.ini", "server/"
    ])

def main():
    parser = argparse.ArgumentParser(description="Форматирование кода")
    parser.add_argument("--check-only", action="store_true", help="Только проверить, не форматировать")
    parser.add_argument("--sort-imports-only", action="store_true", help="Только сортировать импорты")
    parser.add_argument("--format-only", action="store_true", help="Только форматировать")
    
    args = parser.parse_args()
    
    success = True
    
    if not args.sort_imports_only:
        if args.check_only:
            success &= run_command([
                "python", "-m", "black", "--config", "pyproject.toml", "--check", "server/"
            ])
        else:
            success &= format_with_black()
    
    if not args.format_only:
        if args.check_only:
            success &= run_command([
                "python", "-m", "isort", "--settings-path", "pyproject.toml", "--check-only", "server/"
            ])
        else:
            success &= sort_imports()
    
    if not args.check_only:
        success &= check_types()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())