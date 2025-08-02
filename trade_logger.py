import os
import datetime
import logging
from config import POSITION_SIZE

class TradeLogger:
    def __init__(self, log_dir="res"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        self.log_file_path = self._get_log_file_path()
        self.start_time = None
        self.initial_balance = POSITION_SIZE
        self.logger = logging.getLogger(self.__class__.__name__)

        # ANSI цвета для консоли
        self.GREEN = '\033[92m'
        self.RED = '\033[91m'
        self.RESET = '\033[0m'
        self.YELLOW = '\033[93m'

    def _get_log_file_path(self):
        base_name = "res_"
        i = 1
        while os.path.exists(os.path.join(self.log_dir, f"{base_name}{i}.txt")):
            i += 1
        return os.path.join(self.log_dir, f"{base_name}{i}.txt")

    def log_start(self):
        self.start_time = datetime.datetime.now()
        log_entry = f"Сессия началась: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\nНачальный баланс: {self.initial_balance:.2f} USDT\n" + "-" * 80 + "\n"
        
        with open(self.log_file_path, 'w', encoding='utf-8') as f:
            f.write(log_entry)
        print(log_entry)

    def log_trade(self, trade_number: int, path: str, net_profit_usd: float, status: str, total_fee: float, new_balance: float):
        log_time = datetime.datetime.now().strftime('%H:%M:%S')
        
        if net_profit_usd >= 0:
            color = self.GREEN
            sign = '+'
        else:
            color = self.RED
            sign = ''

        # Формируем сообщение для файла (без цветов)
        file_log = (
            f"[{log_time}] Сделка #{trade_number}: {path} | Статус: {status} | "
            f"Чистая прибыль: {sign}{net_profit_usd:.4f} USDT | "
            f"Комиссия: {total_fee:.4f} USDT | "
            f"Новый баланс: {new_balance:.4f} USDT\n"
        )
        
        # Формируем сообщение для консоли (с цветами)
        console_log = (
            f"[{log_time}] Сделка #{trade_number}: {self.YELLOW}{path}{self.RESET} | Статус: {status} | "
            f"Чистая прибыль: {color}{sign}{net_profit_usd:.4f} USDT{self.RESET} | "
            f"Комиссия: {total_fee:.4f} USDT | "
            f"Новый баланс: {self.GREEN}{new_balance:.4f} USDT{self.RESET}"

        )

        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(file_log)
        
        print(console_log)

    def log_end(self, final_balance: float):
        if not self.start_time:
            return

        end_time = datetime.datetime.now()
        duration = end_time - self.start_time
        total_net_profit = final_balance - self.initial_balance
        
        if total_net_profit >= 0:
            color = self.GREEN
            sign = '+'
        else:
            color = self.RED
            sign = ''

        log_entry = (
            "-" * 80 + "\n"
            f"Сессия завершена: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Продолжительность: {str(duration).split('.')[0]}\n"
            f"Итоговый баланс: {final_balance:.4f} USDT\n"
            f"Общая чистая прибыль: {sign}{total_net_profit:.4f} USDT\n"
        )

        console_log = (
             "-" * 80 + "\n"
            f"Сессия завершена: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Продолжительность: {str(duration).split('.')[0]}\n"
            f"Итоговый баланс: {self.GREEN}{final_balance:.4f} USDT{self.RESET}\n"
            f"Общая чистая прибыль: {color}{sign}{total_net_profit:.4f} USDT{self.RESET}\n"
        )

        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        print(console_log)
