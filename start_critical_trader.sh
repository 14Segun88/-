#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}    CRITICAL TRADER MONITOR - PROFESSIONAL 10/10       ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 не установлен!${NC}"
    echo "Установите Python 3: sudo apt-get install python3"
    exit 1
fi

# Проверка наличия файла монитора
if [ ! -f "real_trader_monitor.py" ]; then
    echo -e "${RED}[ERROR] Файл real_trader_monitor.py не найден!${NC}"
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
echo -e "${GREEN}[INFO] Запускаю Trader Monitor с проф. порогами 10/10...${NC}"
echo ""
echo -e "${YELLOW}Критические метрики:${NC}"
echo "  ✅ Латентность ордеров: ≤100ms"
echo "  ✅ Fill Rate: ≥95%"
echo "  ✅ Win Rate: ≥60%"
echo "  ✅ Риски: ≤2%"
echo "  ✅ Stop-loss: 1.0%"
echo ""
echo -e "${YELLOW}Для остановки нажмите Ctrl+C${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""

# Запуск с обработкой ошибок
python3 -u real_trader_monitor.py 2>&1 | tee -a logs/trader_monitor_$(date +%Y%m%d_%H%M%S).log

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
