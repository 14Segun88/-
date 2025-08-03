import logging
import time
from typing import Dict, Optional, List, Tuple
import pandas as pd
from rich.console import Console
from datetime import datetime

from htx_api import HtxApi
from trade_logger import TradeLogger

console = Console()

class TriangularArbitrageStrategy:
    """Класс для реализации стратегии треугольного арбитража."""

    def __init__(self, data: Optional[Dict[str, pd.DataFrame]] = None, 
                 api_client: Optional[HtxApi] = None, 
                 trade_logger: Optional[TradeLogger] = None, 
                 min_profit_threshold: float = 0.1, 
                 position_size: float = 15.0, 
                 fee_rate: float = 0.002):
        """Инициализация стратегии."""
        self.data = data
        self.api_client = api_client
        self.trade_logger = trade_logger
        self.app_logger = logging.getLogger(__name__)
        self.min_profit_threshold = min_profit_threshold
        self.position_size = position_size
        self.balance = position_size 
        self.running = False
        self.symbols = ['btcusdt', 'ethusdt', 'ethbtc']
        self.start_time = None

        if api_client:
            self.fees = self._get_fees_from_api()
        else:
            self.app_logger.warning("API клиент не предоставлен. Используются комиссии по умолчанию.")
            self.fees = {s: fee_rate for s in self.symbols}

    def _get_fees_from_api(self) -> Dict[str, float]:
        """Получает актуальные комиссии с биржи."""
        fees = {}
        for symbol in self.symbols:
            try:
                fees[symbol] = 0.002 
            except Exception as e:
                self.app_logger.error(f"Не удалось получить комиссию для {symbol}: {e}")
                fees[symbol] = 0.002
        return fees

    def start(self):
        """Запускает основной цикл стратегии."""
        self.running = True
        self.start_time = datetime.now()
        console.print(f"Сессия началась: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}", style="bold green")
        console.print(f"Начальный баланс: {self.balance:.4f} USDT")
        console.print("-" * 80)

    def stop(self):
        """Останавливает стратегию."""
        self.running = False
        if self.start_time:
            duration = datetime.now() - self.start_time
            console.print(f"Продолжительность: {str(duration).split('.')[0]}")
        console.print("-" * 80)
        console.print(f"Сессия завершена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="bold red")
        color = "green" if self.balance >= self.position_size else "red"
        console.print(f"Итоговый баланс: [bold {color}]{self.balance:.4f} USDT[/bold {color}]")
        profit = self.balance - self.position_size
        sign = "+" if profit >= 0 else ""
        console.print(f"Общая чистая прибыль: [bold {color}]{sign}{profit:.4f} USDT[/bold {color}]")

    def run(self):
        """Основной цикл работы стратегии."""
        if self.data:
            return self._run_backtest()
        else:
            self._run_live()

    def _run_live(self):
        """Основной цикл для живой торговли."""
        self.start()
        while self.running:
            try:
                market_data = self.get_market_data()
                if market_data:
                    result = self.calculate_arbitrage(market_data)
                    if result:
                        self.execute_trade(result['path_name'], result['profit_percent'])
                time.sleep(10)
            except KeyboardInterrupt:
                self.stop()
                break

    def _run_backtest(self):
        """Запускает бэктест на исторических данных."""
        df_list = [df.add_prefix(f'{symbol}_') for symbol, df in self.data.items()]
        combined_df = pd.concat(df_list, axis=1).dropna()

        for timestamp, row in combined_df.iterrows():
            market_data = {}
            for symbol in self.symbols:
                close_col = f'{symbol}_close'
                if close_col in row and pd.notna(row[close_col]):
                    market_data[symbol] = {'bid': row[close_col], 'ask': row[close_col]}
            
            if len(market_data) != len(self.symbols):
                continue

            result = self.calculate_arbitrage(market_data)
            if result:
                result['timestamp'] = timestamp
                yield result

    def calculate_arbitrage(self, market_data: Dict) -> Optional[Dict]:
        """Рассчитывает потенциальную прибыль, используя цены bid/ask, и возвращает детали сделки."""
        paths = {
            "USDT->ETH->BTC->USDT": (['ethusdt', 'ethbtc', 'btcusdt'], 'buy-sell-sell'),
            "USDT->BTC->ETH->USDT": (['btcusdt', 'ethbtc', 'ethusdt'], 'buy-buy-sell')
        }
        best_profit = -100
        best_path_details = None

        for path_name, (path_symbols, path_ops) in paths.items():
            try:
                ops = path_ops.split('-')
                rate1 = market_data[path_symbols[0]]['ask' if ops[0] == 'buy' else 'bid']
                rate2 = market_data[path_symbols[1]]['ask' if ops[1] == 'buy' else 'bid']
                rate3 = market_data[path_symbols[2]]['ask' if ops[2] == 'buy' else 'bid']

                fee1, fee2, fee3 = self.fees[path_symbols[0]], self.fees[path_symbols[1]], self.fees[path_symbols[2]]

                amount1 = self.position_size
                amount2 = (amount1 / rate1 if ops[0] == 'buy' else amount1 * rate1) * (1 - fee1)
                amount3 = (amount2 * rate2 if ops[1] == 'sell' else amount2 / rate2) * (1 - fee2)
                final_amount = (amount3 * rate3 if ops[2] == 'sell' else amount3 / rate3) * (1 - fee3)

                profit_percent = (final_amount - self.position_size) / self.position_size * 100

                if profit_percent > best_profit:
                    best_profit = profit_percent
                    best_path_details = {
                        'path_name': path_name,
                        'profit_percent': profit_percent,
                        'initial_amount': self.position_size,
                        'steps': [
                            {'symbol': path_symbols[0], 'operation': ops[0], 'rate': rate1, 'amount_after': amount2},
                            {'symbol': path_symbols[1], 'operation': ops[1], 'rate': rate2, 'amount_after': amount3},
                            {'symbol': path_symbols[2], 'operation': ops[2], 'rate': rate3, 'amount_after': final_amount}
                        ]
                    }
            except (TypeError, ZeroDivisionError, KeyError):
                continue

        if best_profit > self.min_profit_threshold:
            return best_path_details
        return None

    def run_divergence_analysis(self):
        """Запускает анализ для сбора всех данных о расхождениях, а не только прибыльных сделок."""
        df_list = [df.add_prefix(f'{symbol}_') for symbol, df in self.data.items()]
        combined_df = pd.concat(df_list, axis=1).dropna()

        for timestamp, row in combined_df.iterrows():
            market_data = {}
            for symbol in self.symbols:
                close_col = f'{symbol}_close'
                if close_col in row and pd.notna(row[close_col]):
                    market_data[symbol] = {'bid': row[close_col], 'ask': row[close_col]}
            
            if len(market_data) != len(self.symbols):
                continue

            result = self.calculate_divergence(market_data)
            if result:
                result['timestamp'] = timestamp
                yield result

    def calculate_divergence(self, market_data: Dict) -> Optional[Dict]:
        """Рассчитывает максимальное расхождение (прибыль/убыток) и ВСЕГДА возвращает его."""
        paths = {
            "USDT->ETH->BTC->USDT": (['ethusdt', 'ethbtc', 'btcusdt'], 'buy-sell-sell'),
            "USDT->BTC->ETH->USDT": (['btcusdt', 'ethbtc', 'ethusdt'], 'buy-buy-sell')
        }
        best_profit = -1000
        best_path_details = None

        for path_name, (path_symbols, path_ops) in paths.items():
            try:
                ops = path_ops.split('-')
                rate1 = market_data[path_symbols[0]]['ask' if ops[0] == 'buy' else 'bid']
                rate2 = market_data[path_symbols[1]]['ask' if ops[1] == 'buy' else 'bid']
                rate3 = market_data[path_symbols[2]]['ask' if ops[2] == 'buy' else 'bid']

                fee1, fee2, fee3 = self.fees[path_symbols[0]], self.fees[path_symbols[1]], self.fees[path_symbols[2]]

                initial_amount = 1
                amount2 = (initial_amount / rate1 if ops[0] == 'buy' else initial_amount * rate1) * (1 - fee1)
                amount3 = (amount2 * rate2 if ops[1] == 'sell' else amount2 / rate2) * (1 - fee2)
                final_amount = (amount3 * rate3 if ops[2] == 'sell' else amount3 / rate3) * (1 - fee3)

                profit_percent = (final_amount - initial_amount) / initial_amount * 100

                if profit_percent > best_profit:
                    best_profit = profit_percent
                    best_path_details = {
                        'path_name': path_name,
                        'profit_percent': profit_percent
                    }
            except (TypeError, ZeroDivisionError, KeyError):
                continue
        
        return best_path_details

    def get_market_data(self) -> Optional[Dict[str, Dict]]:
        """Получает текущие рыночные данные для всех символов."""
        try:
            market_data = {}
            for symbol in self.symbols:
                data = self.api_client.get_market_data(symbol)
                if not data:
                    return None
                market_data[symbol] = data
            return market_data
        except Exception as e:
            self.app_logger.error(f"Ошибка при получении рыночных данных: {e}")
            return None

    def execute_trade(self, path: str, profit_percent: float):
        """Выполняет симуляцию сделки и логирует ее."""
        profit_amount = self.position_size * (profit_percent / 100)
        self.balance += profit_amount
        if self.trade_logger:
            self.trade_logger.log_trade(
                path=path, 
                profit_percent=profit_percent, 
                profit_amount=profit_amount, 
                new_balance=self.balance
            )
        console.print(f"[DEMO] Расчетная чистая прибыль: {profit_amount:.4f} USDT")