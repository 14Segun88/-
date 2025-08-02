import logging
import time
from typing import Dict, Optional, Tuple

import pandas as pd
import config
from htx_api import HtxApi
from trade_logger import TradeLogger


class TriangularArbitrageStrategy:
    """Реализует стратегию треугольного арбитража."""

    def __init__(self, logger: TradeLogger, min_profit_threshold: float, position_size: float, fee_rate: float, api: HtxApi = None, data: Dict[str, pd.DataFrame] = None):
        self.api = api
        self.data = data
        self.symbols = ['btcusdt', 'ethusdt', 'ethbtc']
        self.trade_logger = logger
        self.min_profit_threshold = min_profit_threshold
        self.position_size = position_size
        self.running = False
        self.logger = logging.getLogger(self.__class__.__name__)

        # Инициализируем комиссии для всех торговых пар
        self.fees = self._initialize_fees(fallback_fee_rate=fee_rate)

        self.balance = self.position_size
        self.trades_executed = 0

    def _initialize_fees(self, fallback_fee_rate: float) -> Dict[str, float]:
        """Инициализирует комиссии для всех торговых пар при старте."""
        self.logger.info("Получение актуальных комиссий с биржи...")
        fees = {}
        # Если нет API (например, в бэктесте), используем значение по умолчанию
        if not self.api:
            self.logger.warning("API клиент не предоставлен. Используются комиссии по умолчанию.")
            for symbol in self.symbols:
                fees[symbol] = fallback_fee_rate
            return fees

        for symbol in self.symbols:
            fee_info = self.api.get_fee_rate(symbol)
            # Используем комиссию тейкера, так как арбитраж требует скорости (рыночные ордера)
            if fee_info and 'taker_fee' in fee_info:
                fees[symbol] = fee_info['taker_fee']
                self.logger.info(f"  - Комиссия для {symbol.upper()}: {fees[symbol] * 100:.4f}%")
            else:
                fees[symbol] = fallback_fee_rate
                self.logger.warning(f"  - Не удалось получить комиссию для {symbol.upper()}. Используется значение по умолчанию: {fallback_fee_rate * 100:.4f}%")
        return fees

    def start(self):
        """Запускает основной цикл стратегии."""
        self.running = True
        self.logger.info("Стратегия запущена.")
        self.trade_logger.log_start()

    def stop(self):
        """Останавливает основной цикл стратегии."""
        self.running = False
        self.logger.info("Получен сигнал на остановку. Завершаю работу...")
        self.trade_logger.log_end(self.balance)

    def run(self):
        """Основной цикл работы стратегии."""
        if self.data:
            # Режим бэктестинга
            self._run_backtest()
        else:
            # Режим живой торговли
            self._run_live()

    def _run_live(self):
        """Основной цикл для живой торговли."""
        while self.running:
            try:
                market_data = self.get_market_data()
                if not market_data:
                    time.sleep(2)
                    continue

                result = self.calculate_arbitrage(market_data)
                if result:
                    profit_percent, path = result
                    self.execute_trade(path, profit_percent)

                time.sleep(2)

            except Exception as e:
                self.logger.error(f"Произошла ошибка в основном цикле: {e}", exc_info=True)
                time.sleep(10)
    
    def _run_backtest(self):
        """Основной цикл работы стратегии для бэктестинга."""
        self.logger.info("Подготовка данных для бэктеста...")
        
        # Данные уже имеют 'timestamp' в качестве индекса. Используем столбец 'close'.
        df_btcusdt = self.data['btcusdt'][['close']].rename(columns={'close': 'btcusdt'})
        df_ethusdt = self.data['ethusdt'][['close']].rename(columns={'close': 'ethusdt'})
        df_ethbtc = self.data['ethbtc'][['close']].rename(columns={'close': 'ethbtc'})

        # Объединяем все данные в один DataFrame, выравнивая по временной метке
        combined_df = df_btcusdt.join(df_ethusdt, how='inner').join(df_ethbtc, how='inner')
        combined_df.dropna(inplace=True)  # Удаляем строки с отсутствующими данными

        self.logger.info(f"Начинается бэктест на {len(combined_df)} свечах.")

        # Итерируемся по каждой временной метке (каждой свече)
        for timestamp, row in combined_df.iterrows():
            if not self.running:
                break
            
            market_data = {
                'btcusdt': {'price': row['btcusdt']},
                'ethusdt': {'price': row['ethusdt']},
                'ethbtc': {'price': row['ethbtc']}
            }

            result = self.calculate_arbitrage(market_data)
            if result:
                profit_percent, path = result
                self.execute_trade(path, profit_percent)
        
        self.logger.info("Бэктест завершен.")
        self.stop()

    def calculate_arbitrage(self, market_data: Dict) -> Optional[Tuple[float, str]]:
        """Рассчитывает потенциальную прибыль для двух возможных путей арбитража."""
        paths = {
            "USDT->ETH->BTC->USDT": (['ethusdt', 'ethbtc', 'btcusdt'], 'buy-sell-sell'),
            "USDT->BTC->ETH->USDT": (['btcusdt', 'ethbtc', 'ethusdt'], 'buy-buy-sell')
        }
        best_profit = -100
        best_path_name = None

        for path_name, (path_symbols, path_ops) in paths.items():
            try:
                rate1 = market_data[path_symbols[0]]['price']
                rate2 = market_data[path_symbols[1]]['price']
                rate3 = market_data[path_symbols[2]]['price']

                fee1 = self.fees[path_symbols[0]]
                fee2 = self.fees[path_symbols[1]]
                fee3 = self.fees[path_symbols[2]]

                ops = path_ops.split('-')
                
                # Рассчитываем, сколько мы получим после 3 сделок
                final_amount = self.position_size
                # Сделка 1
                final_amount = (final_amount / rate1 if ops[0] == 'buy' else final_amount * rate1) * (1 - fee1)
                # Сделка 2
                final_amount = (final_amount * rate2 if ops[1] == 'sell' else final_amount / rate2) * (1 - fee2)
                # Сделка 3
                final_amount = (final_amount * rate3 if ops[2] == 'sell' else final_amount / rate3) * (1 - fee3)

                profit_percent = (final_amount - self.position_size) / self.position_size * 100

                if profit_percent > best_profit:
                    best_profit = profit_percent
                    best_path_name = path_name

            except (TypeError, ZeroDivisionError):
                continue # Если нет цены, пропускаем этот путь

        if best_profit > self.min_profit_threshold:
            return best_profit, best_path_name
        
        return None

    def get_market_data(self) -> Optional[Dict[str, Dict]]:
        """Получает рыночные данные для всех отслеживаемых символов."""
        return self.api.get_market_data(self.symbols)

    def execute_trade(self, path: str, profit_percent: float):
        """Логирует найденную возможность для арбитража."""
        self.trades_executed += 1
        new_balance = self.balance * (1 + profit_percent / 100)
        profit_amount = new_balance - self.balance
        self.balance = new_balance

        # В бэктесте мы не можем рассчитать реальную комиссию, поэтому передаем 0
        # Статус всегда 'COMPLETED', так как мы симулируем исполненные сделки
        self.trade_logger.log_trade(
            trade_number=self.trades_executed,
            path=path,
            net_profit_usd=profit_amount,
            status='COMPLETED',
            total_fee=0, # Заглушка для комиссии
            new_balance=self.balance
        )
        self.logger.info(f"[DEMO] Расчетная чистая прибыль: {profit_amount:.4f} USDT")


