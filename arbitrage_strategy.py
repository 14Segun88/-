import logging
import time
import datetime
from typing import Dict, NamedTuple

import config

# Структура для хранения результата расчета
class ArbitrageOpportunity(NamedTuple):
    percentage_diff: float
    signal: str

class TriangularArbitrageStrategy:
    """Класс стратегии треугольного арбитража, адаптированный для HTX."""

    def __init__(self, api, logger, min_profit_threshold: float = 0.1, position_size: float = 15):
        self.api = api
        self.trade_logger = logger
        self.min_profit_threshold = min_profit_threshold
        self.symbols = config.SYMBOLS
        self.position_size = position_size
        self.running = False
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Статистика
        self.checks_done = 0
        self.opportunities_found = 0
        self.trades_executed = 0
        self.estimated_profit_usdt = 0.0

    def calculate_arbitrage(self, market_data: Dict) -> ArbitrageOpportunity:
        """Расчет арбитражной возможности по двум схемам."""
        self.checks_done += 1
        try:
            price_btcusdt = market_data['BTCUSDT']['price']
            price_ltcusdt = market_data['LTCUSDT']['price']
            price_ltcbtc = market_data['LTCBTC']['price']

            # Схема 1: USDT -> BTC -> LTC -> USDT (Продаем BTC в середине)
            rate1 = (1 / price_btcusdt) * (1 / price_ltcbtc) * price_ltcusdt
            percentage_diff1 = (rate1 - 1) * 100

            # Схема 2: USDT -> LTC -> BTC -> USDT (Покупаем BTC в середине)
            rate2 = (1 / price_ltcusdt) * price_ltcbtc * price_btcusdt
            percentage_diff2 = (rate2 - 1) * 100

            if percentage_diff1 > self.min_profit_threshold and percentage_diff1 > percentage_diff2:
                self.opportunities_found += 1
                return ArbitrageOpportunity(percentage_diff=percentage_diff1, signal='SELL_BTC_IN_MIDDLE')
            elif percentage_diff2 > self.min_profit_threshold:
                self.opportunities_found += 1
                return ArbitrageOpportunity(percentage_diff=percentage_diff2, signal='BUY_BTC_IN_MIDDLE')

            return ArbitrageOpportunity(percentage_diff=0, signal='HOLD')
        except (KeyError, ZeroDivisionError) as e:
            self.logger.error(f"Ошибка при расчете арбитража: {e}")
            return ArbitrageOpportunity(percentage_diff=0, signal='HOLD')

    def execute_trade(self, opportunity: ArbitrageOpportunity, market_data: Dict):
        """Выполнение цепочки из трех сделок для извлечения прибыли."""
        self.logger.info(f"[!] Найдена возможность: {opportunity.signal}, профит: {opportunity.percentage_diff:.4f}%. Начинаю выполнение... ")
        
        # В ДЕМО-РЕЖИМЕ ПРОСТО ЛОГИРУЕМ СДЕЛКУ
        if config.DEMO_MODE:
            profit = self.position_size * (opportunity.percentage_diff / 100)
            self.trades_executed += 1
            self.estimated_profit_usdt += profit
            self.logger.info(f"[DEMO SUCCESS] Симуляция успешной сделки. Расчетная прибыль: {profit:.4f} USDT")
            self.trade_logger.log_trade(self.trades_executed, opportunity.signal, profit, "SUCCESS (DEMO)")
            return

        # --- ЛОГИКА ДЛЯ РЕАЛЬНОЙ ТОРГОВЛИ ---
        price_btcusdt = market_data['BTCUSDT']['price']
        price_ltcusdt = market_data['LTCUSDT']['price']
        price_ltcbtc = market_data['LTCBTC']['price']
        order1, order2, order3 = None, None, None

        try:
            if opportunity.signal == 'SELL_BTC_IN_MIDDLE':
                btc_amount = self.position_size / price_btcusdt
                ltc_amount = btc_amount / price_ltcbtc
                order1 = self.api.place_order('btcusdt', 'BUY', self.position_size)
                order2 = self.api.place_order('ltcbtc', 'BUY', btc_amount)
                order3 = self.api.place_order('ltcusdt', 'SELL', ltc_amount)
            elif opportunity.signal == 'BUY_BTC_IN_MIDDLE':
                ltc_amount = self.position_size / price_ltcusdt
                btc_amount = ltc_amount * price_ltcbtc
                order1 = self.api.place_order('ltcusdt', 'BUY', self.position_size)
                order2 = self.api.place_order('ltcbtc', 'SELL', ltc_amount)
                order3 = self.api.place_order('btcusdt', 'SELL', btc_amount)
        except Exception as e:
            self.logger.error(f"Ошибка во время выполнения цепочки '{opportunity.signal}': {e}")

        order_results = [order1, order2, order3]
        if all(order_results):
            profit = self.position_size * (opportunity.percentage_diff / 100)
            self.trades_executed += 1
            self.estimated_profit_usdt += profit
            self.logger.info(f"[SUCCESS] Арбитражная цепочка успешно выполнена. Расчетная прибыль: {profit:.4f} USDT")
            self.trade_logger.log_trade(self.trades_executed, opportunity.signal, profit, "SUCCESS")
        else:
            self.logger.error("[FAIL] Ошибка при выполнении арбитражной цепочки. Не все ордера прошли.")
            # Логируем неудачную сделку с нулевой прибылью
            self.trade_logger.log_trade(self.trades_executed + 1, opportunity.signal, 0, "FAIL")

    def run(self):
        """Основной цикл работы стратегии."""
        self.running = True
        self.logger.info("Стратегия запущена. Нажмите Ctrl+C для остановки.")
        while self.running:
            try:
                market_data = self.api.get_market_data(self.symbols)
                if market_data:
                    opportunity = self.calculate_arbitrage(market_data)
                    if opportunity.signal != 'HOLD':
                        self.execute_trade(opportunity, market_data)
                time.sleep(config.CHECK_INTERVAL)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                self.logger.critical(f"Критическая ошибка в главном цикле: {e}", exc_info=True)
                time.sleep(10)
    
    def stop(self):
        """Остановка стратегии."""
        if self.running:
            self.running = False
            self.logger.info("Получен сигнал на остановку. Завершаю работу...")


