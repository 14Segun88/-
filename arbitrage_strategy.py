import ccxt
from typing import Tuple, Optional, Dict, List
import json
import logging
from generate_detailed_report import generate_report
import pandas as pd
from datetime import datetime
import os
from itertools import permutations

class TriangularArbitrageStrategy:
    """
    Стратегия для поиска возможностей треугольного арбитража в реальном времени.
    """
    def __init__(self, tickers: List[str], min_profit_threshold: float, position_size: float, fee_rate: float, trade_logger, exchange, exchange_name: str):
        # --- ИНИЦИАЛИЗАЦИЯ СТРАТЕГИИ ---
        # exchange: Экземпляр ccxt для взаимодействия с биржей.
        # exchange_name: Название биржи (например, 'Binance').
        # tickers: Список торговых пар для отслеживания.
        # min_profit_threshold: Минимальный процент прибыли для логирования сделки.
        # position_size: Размер позиции в USDT для симуляции сделок.
        # fee_rate: Комиссия биржи за одну сделку.
        # trade_logger: Логгер для записи совершенных сделок.
        self.exchange = exchange
        self.exchange_name = exchange_name
        self.trade_logger = trade_logger
        self.tickers = tickers
        self.min_profit_threshold = min_profit_threshold
        self.position_size = position_size
        self.fee_rate = fee_rate

        self.market_data = {symbol: {'bids': [], 'asks': []} for symbol in self.tickers}
        self.fees = {symbol: self.fee_rate for symbol in self.tickers}
        self.paths = self._find_arbitrage_paths()
        logging.info(f"Found {len(self.paths)} potential arbitrage paths.")
        for path_name in self.paths.keys():
            logging.info(f"  - {path_name}")
        
        self.divergence_data = []
        self.start_time = datetime.now()
        self.paper_balance = self.position_size
        self.trade_count = 0
        self.trade_log = []
        
        logging.info("Arbitrage strategy instance created and ready.")

    def update_market_data(self, symbol: str, market_data: Dict[str, list]):
        if 'bids' in market_data and 'asks' in market_data:
            self.market_data[symbol] = {
                'bids': market_data['bids'],
                'asks': market_data['asks'],
            }

    def _find_arbitrage_paths(self) -> dict:
        # --- ПОИСК АРБИТРАЖНЫХ ПУТЕЙ ---
        # Динамически находит все возможные треугольные цепочки из заданного списка тикеров.
        # Пример: из [BTC/USDT, ETH/USDT, ETH/BTC] находит путь USDT -> BTC -> ETH -> USDT.
        # Возвращает словарь, где ключ - это имя пути (C1->C2->C3->C1), 
        # а значение - кортеж из списка пар и последовательности операций ('buy-sell-sell').
        paths = {}
        all_currencies = set()
        for symbol in self.tickers:
            base, quote = symbol.split('/')
            all_currencies.add(base)
            all_currencies.add(quote)

        for p in permutations(list(all_currencies), 3):
            c1, c2, c3 = p
            path_symbols = []
            
            if f"{c2}/{c1}" in self.tickers:
                path_symbols.append(f"{c2}/{c1}")
            elif f"{c1}/{c2}" in self.tickers:
                path_symbols.append(f"{c1}/{c2}")
            else: continue

            if f"{c3}/{c2}" in self.tickers:
                path_symbols.append(f"{c3}/{c2}")
            elif f"{c2}/{c3}" in self.tickers:
                path_symbols.append(f"{c2}/{c3}")
            else: continue

            if f"{c1}/{c3}" in self.tickers:
                path_symbols.append(f"{c1}/{c3}")
            elif f"{c3}/{c1}" in self.tickers:
                path_symbols.append(f"{c3}/{c1}")
            else: continue
            
            ops = []
            temp_c = c1
            for symbol in path_symbols:
                base, quote = symbol.split('/')
                if base == temp_c:
                    ops.append('sell')
                    temp_c = quote
                else:
                    ops.append('buy')
                    temp_c = base
            
            path_name = f"{c1}->{c2}->{c3}->{c1}"
            paths[path_name] = (path_symbols, '-'.join(ops))

        return paths

    def _get_vwap_price(self, symbol: str, amount_to_process: float, order_type: str) -> Tuple[Optional[float], Optional[float]]:
        # --- РАСЧЕТ VWAP ДЛЯ СИМУЛЯЦИИ ПРОСКАЛЬЗЫВАНИЯ ---
        # Рассчитывает средневзвешенную цену исполнения (VWAP) для заданного объема.
        # Проходит по стакану заявок (asks для покупки, bids для продажи), чтобы симулировать,
        # как крупный ордер влияет на цену (slippage).
        # Args:
        #     symbol: Торговая пара (например, 'BTC/USDT').
        #     amount_to_process: Объем, который нужно купить или продать.
        #         - Для 'buy': это объем в валюте КОТИРОВКИ (сколько USDT мы тратим).
        #         - Для 'sell': это объем в БАЗОВОЙ валюте (сколько BTC мы продаем).
        #     order_type: 'buy' или 'sell'.
        # Returns:
        #     Кортеж (средневзвешенная цена, итоговый объем) или (None, None) в случае ошибки.
        order_book = self.market_data.get(symbol)
        if not order_book or not order_book.get('asks') or not order_book.get('bids'):
            return None, None

        levels = order_book['asks'] if order_type == 'buy' else order_book['bids']
        
        total_value = 0
        total_volume = 0
        volume_to_fill = amount_to_process

        if order_type == 'buy': # Мы тратим quote, чтобы купить base
            for price, volume in levels:
                level_value = price * volume
                if total_value + level_value >= volume_to_fill:
                    remaining_value = volume_to_fill - total_value
                    total_volume += remaining_value / price
                    total_value += remaining_value
                    break
                else:
                    total_value += level_value
                    total_volume += volume
            if total_value < volume_to_fill * 0.99:
                return None, None
            return total_value / total_volume if total_volume > 0 else None, total_volume
        else: # Мы продаем base, чтобы получить quote
            for price, volume in levels:
                if total_volume + volume >= volume_to_fill:
                    remaining_volume = volume_to_fill - total_volume
                    total_value += remaining_volume * price
                    total_volume += remaining_volume
                    break
                else:
                    total_volume += volume
                    total_value += volume * price
            if total_volume < volume_to_fill * 0.99:
                return None, None
            return total_value / total_volume if total_volume > 0 else None, total_value

    def _is_trade_valid(self, symbol: str, amount_base: float, cost_quote: float) -> bool:
        # --- ПРОВЕРКА ЛИМИТОВ СДЕЛКИ ---
        # Проверяет, соответствует ли симулируемая сделка минимальным требованиям биржи по объему.
        # Args:
        #     symbol: Торговая пара.
        #     amount_base: Объем сделки в базовой валюте.
        #     cost_quote: Объем сделки в валюте котировки.
        # Returns:
        #     True, если сделка проходит по лимитам, иначе False.
        limits = self.exchange.markets[symbol].get('limits', {})
        min_amount = limits.get('amount', {}).get('min')
        min_cost = limits.get('cost', {}).get('min')

        if min_amount and amount_base < min_amount:
            return False
        if min_cost and cost_quote < min_cost:
            return False
        return True

    def calculate_all_paths_profit(self) -> List[Dict]:
        # --- ГЛАВНЫЙ МЕТОД РАСЧЕТА ПРИБЫЛИ ---
        # Итерирует по всем найденным арбитражным путям и рассчитывает потенциальную прибыль для каждого.
        # Использует VWAP для реалистичной оценки цены исполнения и проверяет лимиты для каждой ноги арбитража.
        # Если какая-либо часть цепочки невыполнима (недостаточная ликвидность, не проходит по лимитам),
        # всему пути присваивается специальное значение прибыли -999.0.
        # Все результаты (включая неудачные) сохраняются для последующего анализа и генерации отчета.
        results = []
        
        for path_name, (path_symbols, path_ops) in self.paths.items():
            try:
                ops = path_ops.split('-')
                
                # Определяем, в какой валюте начинаем. Если первая пара содержит USDT, начинаем в USDT.
                # Иначе, предполагаем, что начинаем в первой валюте пути.
                c1, c2, c3, _ = path_name.split('->')
                base1, quote1 = path_symbols[0].split('/')
                
                if quote1 == 'USDT' or base1 == 'USDT':
                    start_currency = 'USDT'
                    current_amount = self.position_size
                else:
                    start_currency = c1
                    # Для не-USDT стартов нужна отдельная логика определения размера позиции
                    # Пока используем заглушку, считая, что всегда стартуем в USDT
                    current_amount = self.position_size

                amount_leg1 = current_amount
                
                # Leg 1
                vwap1, amount_after_leg1 = self._get_vwap_price(path_symbols[0], amount_leg1, ops[0])
                is_valid = vwap1 is not None and self._is_trade_valid(path_symbols[0], amount_after_leg1 if ops[0] == 'buy' else amount_leg1, amount_leg1 if ops[0] == 'buy' else amount_after_leg1)
                if not is_valid: 
                    profit_percent = -999.0
                else:
                    amount_leg2 = amount_after_leg1 * (1 - self.fee_rate)

                    # Leg 2
                    vwap2, amount_after_leg2 = self._get_vwap_price(path_symbols[1], amount_leg2, ops[1])
                    is_valid = vwap2 is not None and self._is_trade_valid(path_symbols[1], amount_after_leg2 if ops[1] == 'buy' else amount_leg2, amount_leg2 if ops[1] == 'buy' else amount_after_leg2)
                    if not is_valid:
                        profit_percent = -999.0
                    else:
                        amount_leg3 = amount_after_leg2 * (1 - self.fee_rate)
                        
                        # Leg 3
                        vwap3, amount_after_leg3 = self._get_vwap_price(path_symbols[2], amount_leg3, ops[2])
                        is_valid = vwap3 is not None and self._is_trade_valid(path_symbols[2], amount_after_leg3 if ops[2] == 'buy' else amount_leg3, amount_leg3 if ops[2] == 'buy' else amount_after_leg3)
                        if not is_valid:
                            profit_percent = -999.0
                        else:
                            final_amount = amount_after_leg3 * (1 - self.fee_rate)
                            profit_percent = ((final_amount - self.position_size) / self.position_size) * 100

                results.append({'path_name': path_name, 'profit_percent': profit_percent})
                self.divergence_data.append((datetime.now(), profit_percent, path_name))

            except Exception:
                results.append({'path_name': path_name, 'profit_percent': -999.0})

        return results

    def log_paper_trade(self, gross_profit_pct, path_name):
        self.trade_count += 1
        net_profit_pct = gross_profit_pct
        profit_usd = self.paper_balance * (net_profit_pct / 100)
        self.paper_balance += profit_usd

        trade_details = {
            'timestamp': datetime.now().isoformat(),
            'path': path_name,
            'gross_profit_pct': gross_profit_pct,
            'net_profit_usd': profit_usd,
            'new_balance_usd': self.paper_balance
        }
        self.trade_log.append(trade_details)
        self.trade_logger.info(json.dumps(trade_details))
        logging.info(
            f"PAPER TRADE: Path: {path_name}, Profit: {gross_profit_pct:.4f}%, Net Gain: ${profit_usd:.4f}, New Balance: ${self.paper_balance:.2f}"
        )

    def save_session(self):
        # --- СОХРАНЕНИЕ СЕССИИ И ГЕНЕРАЦИЯ ОТЧЕТА ---
        # Вызывается при завершении работы бота (Ctrl+C).
        # 1. Сохраняет лог совершенных "бумажных" сделок в JSON-файл.
        # 2. Собирает все данные о расхождениях (даже с убытком) и передает их
        #    в модуль generate_detailed_report для создания итогового PNG-отчета.
        if not self.trade_log and not self.divergence_data:
            logging.info("No data to save. Exiting.")
            return

        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        stats_dir = os.path.join('statistics', self.exchange_name.lower())
        os.makedirs(stats_dir, exist_ok=True)

        if self.trade_log:
            log_filename = os.path.join(stats_dir, f'{self.exchange_name.lower()}_trades_{timestamp}.json')
            with open(log_filename, 'w') as f:
                json.dump(self.trade_log, f, indent=4)
            logging.info(f"Trade log saved to {log_filename}")
        else:
            logging.warning("No paper trades were executed in this session.")

        if not self.divergence_data or len(self.divergence_data[0]) != 3:
            logging.error("Divergence data is empty or has incorrect format. Cannot generate PNG report.")
            return

        df = pd.DataFrame(self.divergence_data, columns=['timestamp', 'profit_percentage', 'path'])
        df.set_index('timestamp', inplace=True)
        
        report_filename = os.path.join(stats_dir, f'{self.exchange_name.lower()}_report_{timestamp}.png')
        try:
            generate_report(df, report_filename, self.exchange_name)
            logging.info(f"Successfully generated detailed report: {report_filename}")
        except Exception as e:
            logging.error(f"Failed to generate detailed PNG report: {e}", exc_info=True)

    def execute_trade(self, path: str, profit_percent: float):
        print(f"ИСПОЛНЕНИЕ СДЕЛКИ: Путь={path}, Прибыль={profit_percent:.4f}%")
        # Здесь будет логика отправки реальных ордеров на биржу