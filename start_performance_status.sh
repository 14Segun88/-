#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   PERFORMANCE STATUS MONITOR - PROFESSIONAL 10/10     ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 не установлен!${NC}"
    echo "Установите Python 3: sudo apt-get install python3"
    exit 1
fi

# Проверка наличия файла монитора
if [ ! -f "real_performance_monitor.py" ]; then
    echo -e "${RED}[ERROR] Файл real_performance_monitor.py не найден!${NC}"
    echo "Убедитесь, что файл находится в текущей директории."
    exit 1
fi

# Проверка запущен ли основной бот
if ! pgrep -f "production_multi_exchange_bot.py" > /dev/null; then
    echo -e "${YELLOW}[WARNING] Основной бот не запущен!${NC}"
    echo -e "${YELLOW}Запустите сначала: python3 production_multi_exchange_bot.py${NC}"
    echo ""
    read -p "Продолжить все равно? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Создание директории для логов если её нет
mkdir -p logs

# Запуск монитора
echo -e "${GREEN}[SUCCESS] Все проверки пройдены!${NC}"
echo -e "${GREEN}[INFO] Запускаю Performance Monitor с проф. порогами 10/10...${NC}"
echo ""
echo -e "${YELLOW}Критические метрики:${NC}"
echo "  ✅ Качество данных: ≥95%"
echo "  ✅ Частота сканирования: ≥1 Hz"
echo "  ✅ Возможности: ≥5 в час / ≥1 в 10 минут"
echo "  ✅ Win Rate: ≥60%"
echo "  ✅ Средняя прибыль: ≥$1"
echo ""
echo -e "${YELLOW}График мониторинга:${NC}"
echo "  00:00-00:15 - Запуск и диагностика"
echo "  00:15-01:00 - Наблюдение за первыми сделками"
echo "  01:00-02:00 - Анализ производительности"
echo "  02:00+ - Оптимизация при необходимости"
echo ""
echo -e "${YELLOW}Для остановки нажмите Ctrl+C${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""

# Запуск с обработкой ошибок
python3 -u real_performance_monitor.py 2>&1 | tee -a logs/performance_monitor_$(date +%Y%m%d_%H%M%S).log

# Обработка кода выхода
if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo ""
    echo -e "${RED}[ERROR] Монитор завершился с ошибкой!${NC}"
    echo -e "${YELLOW}Проверьте логи в директории logs/${NC}"
    exit 1
else
    echo ""
    echo -e "${GREEN}[INFO] Монитор успешно завершен.${NC}"
fi
echo "📄 Поиск лог файлов..."
LOG_FILES_FOUND=0

for pattern in "production_bot.log" "critical_*.log" "*.log"; do
    if ls $pattern 1> /dev/null 2>&1; then
        LOG_FILES_FOUND=1
        echo "✅ Найдены лог файлы: $pattern"
        break
    fi
done

if [ $LOG_FILES_FOUND -eq 0 ]; then
    echo "⚠️  Лог файлы не найдены. Монитор будет работать с базовыми данными."
fi

# Проверка файла монитора
if [ ! -f "performance_status_monitor.py" ]; then
    echo "❌ Файл performance_status_monitor.py не найден"
    exit 1
fi

echo "✅ Performance Status Monitor готов к запуску"
echo ""
echo "🚀 Запуск Performance Status Monitor..."
echo "   Показывает статус за 5 минут и 1 час"
echo "   🟢 Зеленый = все отлично"
echo "   🟡 Желтый = хорошо"  
echo "   🔴 Красный = требует внимания"
echo "   Нажмите Ctrl+C для остановки"
echo ""

# Запуск монитора
python3 performance_status_monitor.py
