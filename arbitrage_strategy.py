from typing import Dict, Optional, List

class TriangularArbitrageStrategy:
    """
    Стратегия для поиска возможностей треугольного арбитража в реальном времени.
    Получает данные из внешнего источника (WebSocket) и производит расчеты.
    """
    def __init__(self, symbols: List[str], min_profit_threshold: float, position_size: float, fee_rate: float):
        self.symbols = symbols
        self.min_profit_threshold = min_profit_threshold
        self.position_size = position_size
        self.fee_rate = fee_rate

        # Словарь для хранения самых свежих рыночных данных (bid/ask)
        self.market_data = {symbol: {'bid': 0, 'ask': 0} for symbol in self.symbols}
        
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
        print("Экземпляр стратегии создан. Готов к приему данных.")

    def update_market_data(self, symbol: str, market_data: Dict):
        """
        Обновляет рыночные данные для указанного символа.
        Принимает словарь с ключами 'bid' и 'ask'.
        """
        if symbol in self.market_data:
            self.market_data[symbol]['bid'] = float(market_data['bid'])
            self.market_data[symbol]['ask'] = float(market_data['ask'])

    def calculate_arbitrage(self) -> Optional[Dict]:
        """
        Рассчитывает потенциальную прибыль по всем арбитражным путям,
        используя самые свежие данные из self.market_data.
        """
        # Проверяем, есть ли у нас данные по всем парам
        for symbol in self.symbols:
            if self.market_data[symbol]['ask'] == 0:
                return None # Данные еще не поступили, расчет невозможен

        best_profit = -100
        best_path_details = None

        for path_name, (path_symbols, path_ops) in self.paths.items():
            try:
                ops = path_ops.split('-')

                # Используем реальные bid/ask из потока данных
                rate1 = self.market_data[path_symbols[0]]['ask' if ops[0] == 'buy' else 'bid']
                rate2 = self.market_data[path_symbols[1]]['ask' if ops[1] == 'buy' else 'bid']
                rate3 = self.market_data[path_symbols[2]]['ask' if ops[2] == 'buy' else 'bid']

                fee1 = self.fees[path_symbols[0]]
                fee2 = self.fees[path_symbols[1]]
                fee3 = self.fees[path_symbols[2]]

                # Расчет цепочки сделок
                amount1 = self.position_size
                # Формула зависит от того, покупаем мы или продаем базовую валюту
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
                # Пропускаем, если данные по какой-то паре еще не пришли
                continue

        if best_profit > self.min_profit_threshold:
            return best_path_details
        
        return None

    def execute_trade(self, path: str, profit_percent: float):
        """
        (Задел на будущее)
        Выполняет симуляцию или реальную сделку и логирует ее.
        """
        print(f"ИСПОЛНЕНИЕ СДЕЛКИ: Путь={path}, Прибыль={profit_percent:.4f}%")
        # Здесь будет логика отправки реальных ордеров на биржу

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
        