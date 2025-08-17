#!/usr/bin/env python3
"""
Demo Trading Startup Script
Скрипт запуска демо торговли
"""

import asyncio
import sys
import os
from datetime import datetime
import signal
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'demo_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info("⚠️ Получен сигнал остановки. Завершение работы...")
    sys.exit(0)

async def check_requirements():
    """Проверка всех требований перед запуском"""
    errors = []
    warnings = []
    
    # Проверка наличия модулей
    try:
        import ccxt
    except ImportError:
        errors.append("❌ Модуль ccxt не установлен. Выполните: pip install ccxt")
    
    try:
        import pandas
    except ImportError:
        errors.append("❌ Модуль pandas не установлен. Выполните: pip install pandas")
    
    try:
        import aiohttp
    except ImportError:
        errors.append("❌ Модуль aiohttp не установлен. Выполните: pip install aiohttp")
    
    try:
        import websockets
    except ImportError:
        warnings.append("⚠️ Модуль websockets не установлен. WebSocket может не работать")
    
    # Проверка файлов
    if not os.path.exists('mega_arbitrage_bot.py'):
        errors.append("❌ Файл mega_arbitrage_bot.py не найден")
    
    if not os.path.exists('risk_manager.py'):
        warnings.append("⚠️ Файл risk_manager.py не найден. Риск-менеджмент будет отключен")
    
    if not os.path.exists('order_executor.py'):
        warnings.append("⚠️ Файл order_executor.py не найден. Исполнение ордеров ограничено")
    
    if not os.path.exists('demo_config.py'):
        warnings.append("⚠️ Файл demo_config.py не найден. Используются настройки по умолчанию")
    
    # Вывод результатов проверки
    if errors:
        print("\n🔴 КРИТИЧЕСКИЕ ОШИБКИ:")
        for error in errors:
            print(f"  {error}")
        return False
    
    if warnings:
        print("\n⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"  {warning}")
    
    print("\n✅ Все критические проверки пройдены")
    return True

async def run_demo_bot():
    """Запуск демо бота"""
    try:
        # Настройка демо окружения
        try:
            import demo_keys
            print("✅ Демо ключи загружены")
        except ImportError:
            print("⚠️ Демо ключи не найдены, используем пустые")
        
        # Импорт основного модуля
        from mega_arbitrage_bot import MegaArbitrageBot
        
        print("\n" + "="*60)
        print("🚀 ЗАПУСК АРБИТРАЖНОГО БОТА В ДЕМО РЕЖИМЕ")
        print("="*60)
        
        # Показываем настройки
        try:
            from demo_config import DEMO_SETTINGS, RISK_LIMITS
            print("\n📊 НАСТРОЙКИ ДЕМО:")
            print(f"  • Начальный баланс: ${DEMO_SETTINGS['initial_balance_usd']}")
            print(f"  • Размер позиции: ${DEMO_SETTINGS['max_position_size']}")
            print(f"  • Мин. профит: {DEMO_SETTINGS['min_profit_threshold']}%")
            print(f"  • Макс. дневной убыток: ${DEMO_SETTINGS['max_daily_loss']}")
            print(f"  • Макс. открытых позиций: {DEMO_SETTINGS['max_open_positions']}")
            print(f"  • Реальные ордера: {'Да' if DEMO_SETTINGS['enable_real_orders'] else 'Нет (Paper Trading)'}")
            
            print("\n🛡️ ЛИМИТЫ РИСКОВ:")
            print(f"  • Макс. проскальзывание: {RISK_LIMITS['max_slippage_pct']}%")
            print(f"  • Таймаут позиции: {RISK_LIMITS['position_timeout_sec']} сек")
            print(f"  • Мин. баланс биржи: ${RISK_LIMITS['min_exchange_balance']}")
        except ImportError:
            print("\n⚠️ Используются настройки по умолчанию")
        
        print("\n" + "="*60)
        print("📝 ИНСТРУКЦИИ:")
        print("  1. Бот работает в демо режиме (Paper Trading)")
        print("  2. Все сделки виртуальные, реальные деньги не используются")
        print("  3. Результаты сохраняются в CSV файл")
        print("  4. Для остановки нажмите Ctrl+C")
        print("="*60 + "\n")
        
        # Создание и запуск бота
        bot = MegaArbitrageBot()
        
        # Настройка обработчиков сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Запуск основного цикла
        logger.info("🟢 Бот запущен. Начинаю мониторинг...")
        await bot.run_bot()
        
    except KeyboardInterrupt:
        logger.info("⚠️ Получено прерывание от пользователя")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("🔴 Бот остановлен")

async def main():
    """Главная функция"""
    print("\n" + "🤖 АРБИТРАЖНЫЙ БОТ - ДЕМО ВЕРСИЯ 1.0 🤖".center(60))
    print("=" * 60)
    
    # Проверка требований
    if not await check_requirements():
        print("\n❌ Запуск невозможен из-за критических ошибок")
        print("Исправьте ошибки и попробуйте снова\n")
        return
    
    # Предупреждение
    print("\n⚠️ ВНИМАНИЕ:")
    print("Это ДЕМО версия для тестирования стратегии.")
    print("НЕ используйте на реальных счетах без тщательного тестирования!")
    
    # Запрос подтверждения
    response = input("\nПродолжить запуск? (y/n): ").lower()
    if response != 'y':
        print("Запуск отменен")
        return
    
    # Запуск бота
    await run_demo_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 До свидания!")
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
