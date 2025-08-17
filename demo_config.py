"""
Demo Trading Configuration
Конфигурация для демо торговли
"""

# ====================== РЕЖИМ ТОРГОВЛИ ======================
TRADING_MODE = "DEMO"  # DEMO, PAPER, REAL
USE_TESTNET = True     # Использовать тестовые сети бирж

# ====================== НАСТРОЙКИ ДЕМО ======================
DEMO_SETTINGS = {
    "initial_balance_usd": 1000.0,  # Начальный баланс для демо
    "max_position_size": 100.0,     # Макс размер позиции
    "min_profit_threshold": 0.3,    # Мин порог прибыли %
    "max_daily_loss": 50.0,         # Макс дневной убыток
    "max_open_positions": 3,        # Макс открытых позиций
    "enable_real_orders": False,    # Реальные ордера (False для демо)
    "log_trades_to_csv": True,      # Логировать сделки в CSV
    "enable_notifications": True    # Уведомления о сделках
}

# ====================== ТЕСТОВЫЕ СЕТИ ======================
TESTNET_ENDPOINTS = {
    "binance": {
        "rest": "https://testnet.binance.vision/api",
        "ws": "wss://testnet.binance.vision/ws",
        "requires_vpn": False
    },
    "bybit": {
        "rest": "https://api-testnet.bybit.com",
        "ws": "wss://stream-testnet.bybit.com",
        "requires_vpn": False
    },
    "okx": {
        "rest": "https://www.okx.com",  # OKX demo через тот же endpoint
        "ws": "wss://wspap.okx.com:8443",
        "demo_trading": True,  # Использует демо-торговлю
        "requires_vpn": False
    },
    "kucoin": {
        "rest": "https://openapi-sandbox.kucoin.com",
        "ws": "wss://push-private-sandbox.kucoin.com",
        "requires_vpn": False
    },
    "mexc": {
        "rest": "https://contract.mexc.com",  # MEXC testnet
        "ws": "wss://contract.mexc.com",
        "requires_vpn": False
    }
}

# ====================== РИСК-МЕНЕДЖМЕНТ ======================
RISK_LIMITS = {
    "max_slippage_pct": 0.5,         # Макс проскальзывание %
    "position_timeout_sec": 30,       # Таймаут позиции
    "min_exchange_balance": 200.0,    # Мин баланс на бирже
    "max_correlation_positions": 2,   # Макс коррелированных позиций
    "cooldown_after_loss_sec": 300,   # Кулдаун после убытка
    "max_consecutive_losses": 3       # Макс последовательных убытков
}

# ====================== МОНИТОРИНГ ======================
MONITORING = {
    "enable_dashboard": True,          # Включить дашборд
    "update_interval_sec": 1,          # Интервал обновления
    "show_pnl": True,                  # Показывать P&L
    "show_opportunities": True,        # Показывать возможности
    "show_executions": True,           # Показывать исполнения
    "alert_on_error": True,           # Алерты при ошибках
    "save_metrics": True               # Сохранять метрики
}

# ====================== ИСПОЛНЕНИЕ ОРДЕРОВ ======================
EXECUTION_SETTINGS = {
    "order_type": "limit",             # limit или market
    "use_ioc": True,                  # Immediate-Or-Cancel
    "retry_attempts": 2,               # Попытки повтора
    "retry_delay_ms": 500,            # Задержка между попытками
    "parallel_execution": True,        # Параллельное исполнение
    "check_balance_before": True,      # Проверка баланса перед сделкой
    "cancel_on_timeout": True          # Отмена по таймауту
}

# ====================== ЛОГИРОВАНИЕ ======================
LOGGING_CONFIG = {
    "level": "INFO",                   # DEBUG, INFO, WARNING, ERROR
    "file_enabled": True,              # Логи в файл
    "console_enabled": True,           # Логи в консоль
    "max_file_size_mb": 50,           # Макс размер файла логов
    "backup_count": 5,                 # Количество бэкапов
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}

# ====================== СИМВОЛЫ ДЛЯ ДЕМО ======================
DEMO_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT", 
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT"
]

# ====================== БЕЗОПАСНОСТЬ ======================
SAFETY_CHECKS = {
    "require_2fa": False,              # Для демо не требуется
    "ip_whitelist": [],                # Белый список IP
    "max_api_keys": 5,                 # Макс количество API ключей
    "encrypt_keys": True,              # Шифровать ключи
    "session_timeout_min": 60,         # Таймаут сессии
    "require_confirmation": False      # Требовать подтверждение (демо)
}

# ====================== СТАТИСТИКА ======================
STATISTICS = {
    "track_performance": True,         # Отслеживать производительность
    "calculate_sharpe": True,          # Рассчитывать Sharpe ratio
    "calculate_max_drawdown": True,    # Рассчитывать просадку
    "export_interval_min": 30,         # Интервал экспорта статистики
    "export_format": "csv"             # Формат экспорта
}

def get_demo_config():
    """Получить полную конфигурацию для демо торговли"""
    return {
        "mode": TRADING_MODE,
        "testnet": USE_TESTNET,
        "demo": DEMO_SETTINGS,
        "endpoints": TESTNET_ENDPOINTS if USE_TESTNET else {},
        "risk": RISK_LIMITS,
        "monitoring": MONITORING,
        "execution": EXECUTION_SETTINGS,
        "logging": LOGGING_CONFIG,
        "symbols": DEMO_SYMBOLS,
        "safety": SAFETY_CHECKS,
        "statistics": STATISTICS
    }

def validate_config():
    """Валидация конфигурации"""
    errors = []
    
    # Проверка режима
    if TRADING_MODE not in ["DEMO", "PAPER", "REAL"]:
        errors.append("Неверный TRADING_MODE")
    
    # Проверка настроек демо
    if DEMO_SETTINGS["max_position_size"] > DEMO_SETTINGS["initial_balance_usd"]:
        errors.append("max_position_size больше initial_balance")
    
    # Проверка рисков
    if RISK_LIMITS["max_slippage_pct"] > 5:
        errors.append("Слишком высокий max_slippage_pct")
    
    return errors

# Автоматическая валидация при импорте
validation_errors = validate_config()
if validation_errors:
    print("⚠️ Ошибки конфигурации:")
    for error in validation_errors:
        print(f"  - {error}")
else:
    print("✅ Конфигурация демо торговли загружена успешно")
