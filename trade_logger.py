import os
import datetime

class TradeLogger:
    """Отвечает за логирование всех тестовых запусков и сделок в отдельные файлы."""

    def __init__(self, log_directory="res"):
        self.log_directory = log_directory
        self.log_file_path = None
        self._setup()

    def _setup(self):
        """Создает директорию и определяет путь к новому файлу лога."""
        os.makedirs(self.log_directory, exist_ok=True)
        test_number = self._get_next_test_number()
        self.log_file_path = os.path.join(self.log_directory, f"res_{test_number}.txt")

    def _get_next_test_number(self):
        """Находит максимальный номер существующего лога и возвращает следующий."""
        try:
            files = os.listdir(self.log_directory)
            if not files:
                return 1
            
            max_num = 0
            for f in files:
                if f.startswith("res_") and f.endswith(".txt"):
                    try:
                        num = int(f.split('_')[1].split('.')[0])
                        if num > max_num:
                            max_num = num
                    except (IndexError, ValueError):
                        continue
            return max_num + 1
        except Exception:
            return 1

    def _write_log(self, message):
        """Записывает сообщение в файл лога."""
        try:
            with open(self.log_file_path, "a", encoding='utf-8') as f:
                f.write(message + "\n")
        except Exception as e:
            # В случае ошибки логирования, выводим ее в основной логгер
            print(f"[CRITICAL] Не удалось записать в файл лога {self.log_file_path}: {e}")

    def log_start(self):
        """Записывает время начала теста."""
        start_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self._write_log(f"начало теста    {start_time}")

    def log_end(self):
        """Записывает время окончания теста."""
        end_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self._write_log(f"тест закончен    {end_time}")

    def log_trade(self, trade_num, signal, profit_usd, status):
        """Записывает информацию о сделке."""
        profit_str = f"+{profit_usd:.2f}$" if profit_usd >= 0 else f"{profit_usd:.2f}$"
        # Пример: 1я сделка | SELL_BTC_IN_MIDDLE | +0.02$ прибыли | SUCCESS (DEMO)
        message = f"{trade_num}-я сделка | {signal} | {profit_str} прибыли | {status}"
        self._write_log(message)
