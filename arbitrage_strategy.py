from typing import Dict, Optional, List
import json
import logging
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import os

class TriangularArbitrageStrategy:
    """
    Стратегия для поиска возможностей треугольного арбитража в реальном времени.
    Получает данные из внешнего источника (WebSocket) и производит расчеты.
    """
    def __init__(self, symbols: List[str], min_profit_threshold: float, position_size: float, fee_rate: float, trade_logger, exchange=None, exchange_name='Huobi'):
        # Если биржа не передана, создаем ее по умолчанию (для совместимости с Huobi)
        if exchange:
            self.exchange = exchange
        else:
            from config import API_CONFIG # Локальный импорт для Huobi
            self.exchange = ccxt.huobi(API_CONFIG)

        self.exchange_name = exchange_name
        self.trade_logger = trade_logger
        self.symbols = symbols
        self.min_profit_threshold = min_profit_threshold
        self.position_size = position_size
        self.fee_rate = fee_rate

        # Словарь для хранения самых свежих рыночных данных (стаканов)
        self.market_data = {symbol: {'bids': [], 'asks': []} for symbol in self.symbols}
        
        # Комиссии для каждой пары
        self.fees = {symbol: self.fee_rate for symbol in self.symbols}

        # Определяем возможные арбитражные пути
        # Убедитесь, что эти пути соответствуют символам в вашем config.py
        self.paths = {
            # USDT -> LTC -> BTC -> USDT
            "USDT->LTC->BTC->USDT": (['LTC/USDT', 'LTC/BTC', 'BTC/USDT'], 'buy-sell-sell'),
            # USDT -> BTC -> LTC -> USDT
            "USDT->BTC->LTC->USDT": (['BTC/USDT', 'LTC/BTC', 'LTC/USDT'], 'buy-buy-sell')
        }
        
        # Список для сбора данных о расхождениях с временными метками
        self.divergence_data = []  # Будет содержать кортежи (timestamp, profit_percentage)

        # --- Статистика сессии ---
        self.start_time = datetime.now()
        self.initial_balance = self.position_size
        self.current_balance = self.position_size
        self.trade_log = [] # Будет хранить {'gross_profit_pct': ..., 'net_profit_pct': ...}
        
        print("Экземпляр стратегии создан. Готов к приему данных.")

    def update_market_data(self, symbol: str, market_data: Dict[str, list]):
        """Обновляет данные стакана для указанного символа."""
        if 'bids' in market_data and 'asks' in market_data:
            self.market_data[symbol] = {
                'bids': market_data['bids'], # [[price, volume], ...]
                'asks': market_data['asks'], # [[price, volume], ...]
            }

    def _calculate_price_impact(self, order_book_side: list, amount_to_process: float, is_buy: bool) -> tuple:
        """
        Рассчитывает среднюю цену исполнения для заданного объема.
        is_buy: True, если мы покупаем базовый актив (тратим котируемый, amount_to_process - это USDT)
        is_buy: False, если мы продаем базовый актив (получаем котируемый, amount_to_process - это BTC/LTC)
        Возвращает (средняя_цена, объем_для_следующей_сделки, может_ли_исполниться_полностью).
        """
        filled_value = 0
        total_volume = 0
        
        if is_buy: # Мы тратим котируемую валюту (USDT), чтобы купить базовую (BTC/LTC)
            cost_to_fill = amount_to_process
            for price, volume in order_book_side:
                level_cost = price * volume
                if filled_value + level_cost >= cost_to_fill:
                    remaining_cost = cost_to_fill - filled_value
                    total_volume += remaining_cost / price
                    filled_value += remaining_cost
                    break
                else:
                    filled_value += level_cost
                    total_volume += volume
            if filled_value < cost_to_fill:
                return 0, 0, False # Недостаточно ликвидности
            avg_price = filled_value / total_volume
            return avg_price, total_volume, True
        else: # Мы продаем базовую валюту (BTC/LTC), чтобы получить котируемую (USDT)
            volume_to_sell = amount_to_process
            for price, volume in order_book_side:
                if total_volume + volume >= volume_to_sell:
                    remaining_volume = volume_to_sell - total_volume
                    filled_value += remaining_volume * price
                    total_volume += remaining_volume
                    break
                else:
                    total_volume += volume
                    filled_value += volume * price
            if total_volume < volume_to_sell:
                return 0, 0, False # Недостаточно ликвидности
            avg_price = filled_value / total_volume
            return avg_price, filled_value, True

    def calculate_arbitrage(self):
        """
        Рассчитывает арбитражную возможность с учетом глубины стакана.
        """
        s1, s2, s3 = self.symbols # BTC/USDT, LTC/USDT, LTC/BTC

        if not all(self.market_data[s]['bids'] and self.market_data[s]['asks'] for s in self.symbols):
            return 0 # Не все данные по стаканам еще доступны

        # --- Цепочка 1: USDT -> BTC -> LTC -> USDT ---
        # 1. Покупаем BTC за USDT (используем asks BTC/USDT)
        price1, btc_amount, can_exec1 = self._calculate_price_impact(self.market_data[s1]['asks'], self.position_size, is_buy=True)
        if not can_exec1:
            return 0
        
        # 2. Продаем BTC, покупаем LTC (используем asks LTC/BTC, т.к. мы покупаем LTC)
        # Здесь мы продаем btc_amount, поэтому is_buy=False не совсем верно. Логика сложнее.
        # Правильно: нам нужно купить LTC на сумму btc_amount. Это эквивалентно продаже BTC.
        # Для пары LTC/BTC, покупая LTC, мы тратим BTC. Это операция покупки.
        price2, ltc_amount, can_exec2 = self._calculate_price_impact(self.market_data[s3]['asks'], btc_amount, is_buy=True)
        if not can_exec2:
             return 0

        # 3. Продаем LTC за USDT (используем bids LTC/USDT)
        price3, final_usdt_amount, can_exec3 = self._calculate_price_impact(self.market_data[s2]['bids'], ltc_amount, is_buy=False)
        if not can_exec3:
            return 0

        profit_percentage = ((final_usdt_amount - self.position_size) / self.position_size) * 100

        # TODO: Добавить вторую цепочку (USDT -> LTC -> BTC -> USDT)

        return profit_percentage

    def log_paper_trade(self, gross_profit_pct):
        """Логирует симулированную сделку и обновляет статистику."""
        total_fee_pct = (1 - (1 - self.fee_rate)**3) * 100
        net_profit_pct = gross_profit_pct - total_fee_pct

        self.trade_log.append({
            'gross_profit_pct': gross_profit_pct,
            'net_profit_pct': net_profit_pct
        })

        # Обновляем баланс
        self.current_balance *= (1 + net_profit_pct / 100)

        # Логируем в файл
        self.trade_logger.info(f"PAPER_TRADE; GROSS: {gross_profit_pct:+.4f}%; NET: {net_profit_pct:+.4f}%; BALANCE: ${self.current_balance:.2f}")
        return net_profit_pct > 0

    def save_divergence_data(self):
        """Сохраняет собранные данные о расхождениях в JSON и строит временной график."""
        if not self.divergence_data:
            logging.info(f"No divergence data from {self.exchange_name} to save.")
            return

        # 1. Определяем путь для сохранения файлов (всё в одной папке биржи)
        exchange_name_lower = self.exchange_name.lower()
        stats_dir = os.path.join('statistics', exchange_name_lower)
        os.makedirs(stats_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 2. Подготавливаем данные для сохранения
        data_to_save = [{'timestamp': ts.isoformat(), 'profit_percentage': profit}
                        for ts, profit in self.divergence_data]
        timestamps = [ts for ts, _ in self.divergence_data]
        profits = [profit for _, profit in self.divergence_data]

        # 3. Сохраняем данные в JSON
        json_filename = os.path.join(stats_dir, f'{exchange_name_lower}_data_{timestamp}.json')
        with open(json_filename, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        logging.info(f"Divergence data saved to {json_filename}")

        # 3. Рассчитываем итоговую статистику для отчета
        end_time = datetime.now()
        duration = end_time - self.start_time
        total_trades = len(self.trade_log)
        profitable_trades = sum(1 for trade in self.trade_log if trade['net_profit_pct'] > 0)
        unprofitable_trades = total_trades - profitable_trades
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        net_pnl = self.current_balance - self.initial_balance
        net_pnl_pct = (net_pnl / self.initial_balance * 100)

        # Форматируем строку со статистикой
        stats_text = (
            f"--- Trading Session Report ---\
" 
            f"Exchange: {self.exchange_name.upper()}\n"
            f"Duration: {str(duration).split('.')[0]}\n"
            f"Start Balance: ${self.initial_balance:.2f}\n"
            f"End Balance:   ${self.current_balance:.2f}\n"
            f"Net P/L: ${net_pnl:+.2f} ({net_pnl_pct:+.2f}%)\n"
            f"\n"
            f"--- Trade Statistics ---\
"
            f"Total Trades: {total_trades}\n"
            f"Profitable Trades: {profitable_trades}\n"
            f"Unprofitable Trades: {unprofitable_trades}\n"
            f"Win Rate: {win_rate:.2f}%"
        )

        # 4. Создаем графики и отчет
        try:
            # Используем GridSpec для сложного макета: текстовый блок сверху, графики снизу
            fig = plt.figure(figsize=(15, 12))
            gs = fig.add_gridspec(3, 1, height_ratios=[1, 2, 2])

            # --- Блок со статистикой ---
            ax0 = fig.add_subplot(gs[0])
            ax0.text(0.5, 0.5, stats_text, ha='center', va='center', fontsize=14, 
                     fontfamily='monospace', bbox=dict(boxstyle="round,pad=0.5", fc="aliceblue", ec="black", lw=1))
            ax0.axis('off') # Скрываем оси у текстового блока

            # --- Графики ---
            ax1 = fig.add_subplot(gs[1])
            ax2 = fig.add_subplot(gs[2])
            
            # График 1: Временной столбчатый график
            if timestamps:
                # Создаем цвета для столбцов
                colors = ['green' if p > 0 else 'red' if p < -0.1 else 'orange' for p in profits]
                
                # Вычисляем ширину столбцов на основе интервала
                if len(timestamps) > 1:
                    avg_interval = (timestamps[-1] - timestamps[0]) / len(timestamps)
                    bar_width = avg_interval * 0.8
                else:
                    bar_width = pd.Timedelta(seconds=1)
                
                ax1.bar(timestamps, profits, width=bar_width, alpha=0.7, color=colors, 
                       edgecolor='black', linewidth=0.1)
                
                ax1.axhline(y=0, color='black', linestyle='-', linewidth=2, label='Breakeven (0%)')
                ax1.axhline(y=np.mean(profits), color='blue', linestyle='--', linewidth=2, 
                          label=f'Mean Profit: {np.mean(profits):.4f}%')
                
                # Устанавливаем фиксированную шкалу Y
                ax1.set_ylim(-0.20, 0.20)
                
                ax1.set_title(f'Arbitrage Opportunities Over Time - {self.exchange_name}', fontsize=14)
                ax1.set_xlabel('Time')
                ax1.set_ylabel('Profit Percentage (%)')
                ax1.grid(True, linestyle='--', alpha=0.3, axis='y')
                
                # Цветовая легенда
                from matplotlib.patches import Patch
                legend_elements = [
                    Patch(facecolor='green', alpha=0.7, label='Profitable (>0%)'),
                    Patch(facecolor='orange', alpha=0.7, label='Small Loss (>-0.1%)'),
                    Patch(facecolor='red', alpha=0.7, label='Big Loss (<-0.1%)')
                ]
                ax1.legend(handles=legend_elements, loc='upper right')
                
                # Поворачиваем подписи времени для читаемости
                plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
            else:
                ax1.text(0.5, 0.5, 'No timestamp data available', 
                        horizontalalignment='center', verticalalignment='center',
                        transform=ax1.transAxes, fontsize=14)
                ax1.set_title('Time Series - No Data')
                ax1.set_ylim(-0.20, 0.20)
            
            # График 2: Гистограмма распределения
            ax2.hist(profits, bins=100, alpha=0.75, color='royalblue')
            ax2.axvline(x=0, color='red', linestyle='--', linewidth=1.5, label='Breakeven')
            ax2.axvline(x=np.mean(profits), color='green', linestyle='-', linewidth=2, 
                       label=f'Mean Profit: {np.mean(profits):.4f}%')
            ax2.set_title('Distribution of Arbitrage Opportunities')
            ax2.set_xlabel('Profit Percentage (%)')
            ax2.set_ylabel('Frequency')
            ax2.grid(True, linestyle='--', alpha=0.6)
            ax2.legend()
            
            plt.tight_layout()
            
            # Сохраняем PNG-отчет (всегда последнюю версию)
            png_filename = os.path.join(stats_dir, f'{exchange_name_lower}_latest_report.png')
            plt.savefig(png_filename, dpi=300, bbox_inches='tight')
            logging.info(f"Arbitrage analysis charts saved to {png_filename}")
            plt.close()

        except Exception as e:
            logging.error(f"Could not create or save charts: {e}")

    

            profit_in_usdt = self.position_size * (final_net_profit_pct / 100)
            self.trade_logger.info(f"RESULT: SUCCESS. Estimated profit: ${profit_in_usdt:.4f}")
        else:
            self.trade_logger.info("RESULT: FAILURE. Opportunity is unprofitable after costs.")
        self.trade_logger.info("-----------------------------------------------------------")

        return final_net_profit_pct

    def calculate_divergence(self) -> Optional[Dict]:
        """
        Рассчитывает максимальное расхождение (прибыль/убыток) для сбора статистики
        и ВСЕГДА возвращает его. Использует самые свежие данные.
        """
        best_profit = -1000  # Начинаем с очень маленького числа
        best_path_details = None

        for path_name, (path_symbols, path_ops) in self.paths.items():
            try:
                ops = path_ops.split('-')

                rate1 = self.market_data[path_symbols[0]]['ask' if ops[0] == 'buy' else 'bid']
                rate2 = self.market_data[path_symbols[1]]['ask' if ops[1] == 'buy' else 'bid']
                rate3 = self.market_data[path_symbols[2]]['ask' if ops[2] == 'buy' else 'bid']

                fee1 = self.fees[path_symbols[0]]
                fee2 = self.fees[path_symbols[1]]
                fee3 = self.fees[path_symbols[2]]

                # Пропускаем расчет, если хотя бы одна из цен еще не пришла (равна 0)
                if rate1 == 0 or rate2 == 0 or rate3 == 0:
                    continue

                # Нормализованный расчет для сравнения
                initial_amount = 1.0
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
                # Эта ошибка нормальна, если данные по одной из пар еще не пришли.
                # Просто пропускаем этот путь и переходим к следующему.
                continue
        
        return best_path_details

    def execute_trade(self, path: str, profit_percent: float):
        """
        (Задел на будущее)
        Выполняет симуляцию или реальную сделку и логирует ее.
        """
        print(f"ИСПОЛНЕНИЕ СДЕЛКИ: Путь={path}, Прибыль={profit_percent:.4f}%")
        # Здесь будет логика отправки реальных ордеров на биржу