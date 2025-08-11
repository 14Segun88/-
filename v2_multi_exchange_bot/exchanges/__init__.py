"""
Exchange module initialization.
Provides dynamic import functionality for exchange classes.
"""

def import_exchange_class(exchange_name: str):
    """
    Динамически импортирует класс биржи по имени.
    
    Args:
        exchange_name: Имя биржи ('binance' или 'kraken')
        
    Returns:
        Класс биржи
    """
    if exchange_name.lower() == 'binance':
        from .binance import BinanceExchange
        return BinanceExchange
    elif exchange_name.lower() == 'kraken':
        from .kraken import KrakenExchange
        return KrakenExchange
    else:
        raise ValueError(f"Unknown exchange: {exchange_name}")