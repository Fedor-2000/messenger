# scripts/analysis/run_analysis.py
#!/usr/bin/env python3
"""
Скрипт для запуска анализа качества кода.
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse
import json
from typing import Dict, List, Optional

def run_command(cmd: List[str], cwd: Optional[str] = None) -> bool:
    """Выполнение команды и проверка результата."""
    print(f"Запуск: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    success = result.returncode == 0
    if not success:
        print(f"Ошибка при выполнении: {' '.join(cmd)}")
    return success

def run_black_check() -> bool:
    """Проверка форматирования с помощью black."""
    print("\n=== Проверка форматирования (black) ===")
    return run_command([
        "python", "-m", "black", "--config", "pyproject.toml", "--check", "server/"
    ])

def run_isort_check() -> bool:
    """Проверка сортировки импортов с помощью isort."""
    print("\n=== Проверка сортировки импортов (isort) ===")
    return run_command([
        "python", "-m", "isort", "--settings-path", "pyproject.toml", "--check-only", "server/"
    ])

def run_flake8_check() -> bool:
    """Проверка стиля кода с помощью flake8."""
    print("\n=== Проверка стиля кода (flake8) ===")
    return run_command([
        "python", "-m", "flake8", "--config", ".flake8", "server/"
    ])

def run_mypy_check() -> bool:
    """Проверка типов с помощью mypy."""
    print("\n=== Проверка типов (mypy) ===")
    return run_command([
        "python", "-m", "mypy", "--config-file", "mypy.ini", "server/"
    ])

def run_bandit_check() -> bool:
    """Проверка безопасности с помощью bandit."""
    print("\n=== Проверка безопасности (bandit) ===")
    return run_command([
        "python", "-m", "bandit", "-c", "pyproject.toml", "-r", "server/"
    ])

def run_pytest_coverage() -> bool:
    """Запуск тестов с покрытием кода."""
    print("\n=== Запуск тестов с покрытием ===")
    return run_command([
        "python", "-m", "pytest", "server/tests/", 
        "-v", "--cov=server/app", "--cov-report=html:reports/coverage_html", 
        "--cov-report=term-missing", "--cov-fail-under=80"
    ])

def run_security_scan() -> bool:
    """Запуск сканирования безопасности."""
    print("\n=== Сканирование безопасности (safety) ===")
    return run_command([
        "safety", "check", "-r", "server/requirements.txt"
    ])

def run_vulnerability_scan() -> bool:
    """Запуск сканирования уязвимостей."""
    print("\n=== Сканирование уязвимостей (dodgy) ===")
    return run_command([
        "dodgy", "--path", "server/"
    ])

def run_complexity_analysis() -> bool:
    """Анализ сложности кода."""
    print("\n=== Анализ сложности кода (radon) ===")
    success1 = run_command(["radon", "cc", "server/app", "-s"])
    success2 = run_command(["radon", "mi", "server/app", "-s"])
    return success1 and success2

def generate_quality_report(results: Dict[str, bool]) -> str:
    """Генерация отчета о качестве кода."""
    report = "Отчет о качестве кода\n"
    report += "=" * 50 + "\n\n"

    for tool, success in results.items():
        status = "✓ ПРОЙДЕНО" if success else "✗ ОШИБКА"
        report += f"{tool}: {status}\n"

    report += f"\nВсего проверок: {len(results)}"
    report += f"\nУспешно пройдено: {sum(results.values())}"
    report += f"\nНе пройдено: {len(results) - sum(results.values())}"

    return report

def main():
    parser = argparse.ArgumentParser(description="Анализ качества кода")
    parser.add_argument("--fix", action="store_true", help="Исправить форматирование")
    parser.add_argument("--full", action="store_true", help="Полный анализ (включая тесты)")
    parser.add_argument("--output", default="reports/", help="Директория для отчетов")

    args = parser.parse_args()

    # Создаем директорию для отчетов
    os.makedirs(args.output, exist_ok=True)

    print("Запуск анализа качества кода...")

    results = {}

    # Основные проверки
    results["Black форматирование"] = run_black_check()
    results["isort сортировка импортов"] = run_isort_check()
    results["Flake8 стиль кода"] = run_flake8_check()
    results["MyPy типизация"] = run_mypy_check()
    results["Bandit безопасность"] = run_bandit_check()
    results["Safety зависимости"] = run_security_scan()

    # Дополнительные проверки
    results["Сложность кода"] = run_complexity_analysis()
    results["Vulnerability scan"] = run_vulnerability_scan()

    if args.full:
        results["Тесты с покрытием"] = run_pytest_coverage()

    # Генерируем отчет
    report = generate_quality_report(results)

    # Сохраняем отчет
    with open(f"{args.output}/quality_report.txt", "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n{report}")

    # Возвращаем код возврата
    all_passed = all(results.values())
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())