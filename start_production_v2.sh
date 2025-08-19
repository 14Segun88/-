#!/bin/bash

echo "🚀 Production Arbitrage Bot v2.0 - 10/10 Ready"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
pip install -q ccxt python-dotenv aiohttp websockets asyncio-throttle 2>/dev/null

# Проверка наличия config.env
if [ ! -f "config.env" ]; then
    echo "❌ Файл config.env не найден!"
    echo "Создайте файл и добавьте API ключи для демо счетов"
    exit 1
fi

# Проверка режима
TRADING_MODE=${1:-demo}

if [ "$TRADING_MODE" == "real" ]; then
    echo "⚠️  ВНИМАНИЕ: Режим REAL торговли!"
    echo "Убедитесь что используете РЕАЛЬНЫЕ API ключи"
    read -p "Продолжить? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Отменено."
        exit 1
    fi
else
    echo "✅ Режим: DEMO (безопасная торговля)"
fi

# Установка переменной окружения
export TRADING_MODE=$TRADING_MODE

# Запуск бота
echo ""
echo "🤖 Запуск бота..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 production_bot_v2.py
