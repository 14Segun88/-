#!/bin/bash

echo "🚀 Запуск 2-часового теста арбитражного бота"
echo "📅 Время старта: $(date)"

# Очистка старых логов
echo "📄 Очистка старых логов..."
> production_bot.log

# Запуск бота с таймаутом 2 часа
echo "⏱️ Бот будет работать 2 часа..."
timeout 7200 python3 start_demo.py

# Сохранение результатов
echo "💾 Сохранение результатов..."
cp production_bot.log "logs/test_2hour_$(date +%Y%m%d_%H%M%S).log"

echo "✅ Тест завершен в $(date)"
echo "📊 Логи сохранены в logs/"
