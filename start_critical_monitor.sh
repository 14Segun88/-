#!/bin/bash

# 🔍 Critical Scanner Monitor Startup Script
# Скрипт запуска критического монитора сканера

echo "🔍 Critical Scanner Monitor - Startup Script"
echo "============================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.7+"
    exit 1
fi

echo "✅ Python3 найден: $(python3 --version)"

# Проверка и установка зависимостей
echo "📦 Проверка зависимостей..."

REQUIRED_PACKAGES=("colorama" "aiohttp")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if ! python3 -c "import $package" 2>/dev/null; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -ne 0 ]; then
    echo "📥 Установка недостающих пакетов: ${MISSING_PACKAGES[*]}"
    pip3 install "${MISSING_PACKAGES[@]}"
    
    if [ $? -ne 0 ]; then
        echo "❌ Ошибка установки зависимостей"
        exit 1
    fi
fi

echo "✅ Все зависимости установлены"

# Проверка наличия лог файлов
echo "📄 Поиск лог файлов бота..."
LOG_FILES_FOUND=0

for pattern in "production_bot.log" "websocket_bot.log" "mega_arbitrage_bot.log" "*bot*.log" "*.log"; do
    if ls $pattern 1> /dev/null 2>&1; then
        LOG_FILES_FOUND=1
        echo "✅ Найдены лог файлы: $pattern"
        break
    fi
done

if [ $LOG_FILES_FOUND -eq 0 ]; then
    echo "⚠️  Лог файлы не найдены. Монитор будет работать только с live данными."
fi

# Проверка файла монитора
if [ ! -f "critical_scanner_monitor.py" ]; then
    echo "❌ Файл critical_scanner_monitor.py не найден"
    exit 1
fi

echo "✅ Критический монитор готов к запуску"
echo ""
echo "🚀 Запуск Critical Scanner Monitor..."
echo "   Нажмите Ctrl+C для остановки"
echo ""

# Запуск монитора
python3 critical_scanner_monitor.py
