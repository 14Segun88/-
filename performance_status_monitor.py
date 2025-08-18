#!/usr/bin/env python3
"""
📊 Performance Status Monitor
Модуль статуса производительности бота на 5 минут и 1 час
"""

import asyncio
import os
import time
import json
import glob
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from colorama import init, Fore, Back, Style
import logging

# Инициализация colorama
init(autoreset=True)

@dataclass
class PerformanceMetrics:
    """Метрики производительности"""
    # 5-минутные метрики
    opportunities_5min: int = 0
    trades_5min: int = 0
    profit_5min: float = 0.0
    errors_5min: int = 0
    
    # Часовые метрики
    opportunities_1hour: int = 0
    trades_1hour: int = 0
    profit_1hour: float = 0.0
    errors_1hour: int = 0
    
    # Статус подключений
    active_exchanges: int = 0
    data_quality: float = 0.0
    scan_frequency: float = 0.0
    
    # Временные метки
    last_update: datetime = None
    start_time: datetime = None

class PerformanceStatusMonitor:
    """Монитор статуса производительности"""
    
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.metrics.start_time = datetime.now()
        self.metrics.last_update = datetime.now()
        
        self.running = False
        self.log_files = []
        self.log_positions = {}
        
        # Пороги для зеленого статуса
        self.thresholds_5min = {
            'min_opportunities': 1,
            'min_trades': 0,
            'min_profit': 0.0,
            'max_errors': 2,
            'min_exchanges': 2,
            'min_data_quality': 90.0,
            'min_scan_freq': 0.8
        }
        
        self.thresholds_1hour = {
            'min_opportunities': 5,
            'min_trades': 1,
            'min_profit': 1.0,
            'max_errors': 10,
            'min_exchanges': 3,
            'min_data_quality': 95.0,
            'min_scan_freq': 1.0
        }
        
        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def find_log_files(self):
        """Поиск лог файлов"""
        patterns = [
            'production_bot.log',
            'critical_scanner_monitor.log',
            'critical_trader_monitor.log',
            'multi_exchange_bot.log',
            'hybrid_bot.log',
            'demo_bot_*.log',
            'new_bot_*.log'
        ]
        
        for pattern in patterns:
            files = glob.glob(pattern)
            self.log_files.extend(files)
        
        # Удаление дубликатов
        self.log_files = list(set(self.log_files))
        self.log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Инициализация позиций
        for log_file in self.log_files:
            self.log_positions[log_file] = 0
    
    async def parse_logs(self):
        """Парсинг логов для извлечения метрик"""
        while self.running:
            try:
                current_time = datetime.now()
                time_5min_ago = current_time - timedelta(minutes=5)
                time_1hour_ago = current_time - timedelta(hours=1)
                
                # Сброс метрик
                self.metrics.opportunities_5min = 0
                self.metrics.trades_5min = 0
                self.metrics.profit_5min = 0.0
                self.metrics.errors_5min = 0
                
                self.metrics.opportunities_1hour = 0
                self.metrics.trades_1hour = 0
                self.metrics.profit_1hour = 0.0
                self.metrics.errors_1hour = 0
                
                for log_file in self.log_files:
                    if os.path.exists(log_file):
                        try:
                            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                                f.seek(self.log_positions.get(log_file, 0))
                                
                                for line in f:
                                    line_time = self.extract_timestamp(line)
                                    if line_time:
                                        await self.parse_line(line, line_time, time_5min_ago, time_1hour_ago)
                                
                                self.log_positions[log_file] = f.tell()
                                
                        except Exception as e:
                            self.logger.error(f"Ошибка чтения {log_file}: {e}")
                
                self.metrics.last_update = current_time
                
            except Exception as e:
                self.logger.error(f"Ошибка парсинга логов: {e}")
            
            await asyncio.sleep(5)  # Обновление каждые 5 секунд
    
    def extract_timestamp(self, line: str) -> Optional[datetime]:
        """Извлечение временной метки из строки лога"""
        try:
            # Формат: 2025-08-15 01:56:59,416 [INFO]
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                return datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
        except:
            pass
        return None
    
    async def parse_line(self, line: str, line_time: datetime, time_5min_ago: datetime, time_1hour_ago: datetime):
        """Парсинг строки лога"""
        try:
            # Возможности арбитража - ищем "Найдено возможностей: X"
            if 'найдено возможностей' in line.lower():
                opps_match = re.search(r'найдено возможностей:\s*(\d+)', line.lower())
                if opps_match:
                    opportunities = int(opps_match.group(1))
                    if opportunities > 0:  # Только если найдены возможности
                        if line_time >= time_5min_ago:
                            self.metrics.opportunities_5min += opportunities
                        if line_time >= time_1hour_ago:
                            self.metrics.opportunities_1hour += opportunities
            
            # Сделки - ищем "Исполнено сделок: X/Y"
            elif 'исполнено сделок' in line.lower():
                trades_match = re.search(r'исполнено сделок:\s*(\d+)/(\d+)', line.lower())
                if trades_match:
                    executed = int(trades_match.group(1))
                    if executed > 0:  # Только если есть исполненные сделки
                        if line_time >= time_5min_ago:
                            self.metrics.trades_5min += executed
                        if line_time >= time_1hour_ago:
                            self.metrics.trades_1hour += executed
            
            # Прибыль - ищем "Общая прибыль: $X.XX"
            elif 'общая прибыль' in line.lower():
                profit_match = re.search(r'общая прибыль:\s*\$?([+-]?\d+\.?\d*)', line.lower())
                if profit_match:
                    profit = float(profit_match.group(1))
                    if profit != 0:  # Только если есть прибыль/убыток
                        if line_time >= time_5min_ago:
                            self.metrics.profit_5min = profit  # Заменяем, а не добавляем
                        if line_time >= time_1hour_ago:
                            self.metrics.profit_1hour = profit
            
            # Ошибки
            elif 'error' in line.lower() or 'ошибка' in line.lower():
                if line_time >= time_5min_ago:
                    self.metrics.errors_5min += 1
                if line_time >= time_1hour_ago:
                    self.metrics.errors_1hour += 1
            
            # Активные биржи - ищем "📊 Активных бирж: X"
            elif 'активных бирж' in line.lower():
                exchanges_match = re.search(r'активных бирж:\s*(\d+)', line.lower())
                if exchanges_match:
                    self.metrics.active_exchanges = int(exchanges_match.group(1))
            
            # Качество данных
            elif 'качество данных' in line.lower() or 'data quality' in line.lower():
                quality_match = re.search(r'(\d+\.?\d*)%', line)
                if quality_match:
                    self.metrics.data_quality = float(quality_match.group(1))
            
            # Частота сканирования
            elif 'частота' in line.lower() or 'frequency' in line.lower():
                freq_match = re.search(r'(\d+\.?\d*)\s*Hz', line)
                if freq_match:
                    self.metrics.scan_frequency = float(freq_match.group(1))
                    
        except Exception as e:
            self.logger.error(f"Ошибка парсинга строки: {e}")
    
    def get_5min_status(self) -> str:
        """Получение статуса за 5 минут"""
        thresholds = self.thresholds_5min
        
        checks = [
            self.metrics.opportunities_5min >= thresholds['min_opportunities'],
            self.metrics.trades_5min >= thresholds['min_trades'],
            self.metrics.profit_5min >= thresholds['min_profit'],
            self.metrics.errors_5min <= thresholds['max_errors'],
            self.metrics.active_exchanges >= thresholds['min_exchanges'],
            self.metrics.data_quality >= thresholds['min_data_quality'],
            self.metrics.scan_frequency >= thresholds['min_scan_freq']
        ]
        
        if all(checks):
            return f"{Fore.GREEN}🟢 ОТЛИЧНО{Style.RESET_ALL}"
        elif sum(checks) >= 5:
            return f"{Fore.YELLOW}🟡 ХОРОШО{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}🔴 ТРЕБУЕТ ВНИМАНИЯ{Style.RESET_ALL}"
    
    def get_1hour_status(self) -> str:
        """Получение статуса за 1 час"""
        thresholds = self.thresholds_1hour
        
        checks = [
            self.metrics.opportunities_1hour >= thresholds['min_opportunities'],
            self.metrics.trades_1hour >= thresholds['min_trades'],
            self.metrics.profit_1hour >= thresholds['min_profit'],
            self.metrics.errors_1hour <= thresholds['max_errors'],
            self.metrics.active_exchanges >= thresholds['min_exchanges'],
            self.metrics.data_quality >= thresholds['min_data_quality'],
            self.metrics.scan_frequency >= thresholds['min_scan_freq']
        ]
        
        if all(checks):
            return f"{Fore.GREEN}🟢 ОТЛИЧНО{Style.RESET_ALL}"
        elif sum(checks) >= 5:
            return f"{Fore.YELLOW}🟡 ХОРОШО{Style.RESET_ALL}"
        else:
            return f"{Fore.RED}🔴 ТРЕБУЕТ ВНИМАНИЯ{Style.RESET_ALL}"
    
    async def display_dashboard(self):
        """Отображение дашборда статуса"""
        while self.running:
            os.system('clear' if os.name == 'posix' else 'cls')
            print(f"\033[2J\033[H")
            
            print(f"{Fore.CYAN}{'='*80}")
            print(f"{Fore.CYAN}📊 PERFORMANCE STATUS MONITOR")
            print(f"{Fore.WHITE}Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{Fore.CYAN}{'='*80}")
            print()
            
            # Статус за 5 минут
            print(f"{Fore.YELLOW}⏱️ СТАТУС ЗА 5 МИНУТ:")
            print(f"Общий статус:        {self.get_5min_status()}")
            print(f"Возможности:         {Fore.CYAN}{self.metrics.opportunities_5min}{Style.RESET_ALL}")
            print(f"Сделки:              {Fore.CYAN}{self.metrics.trades_5min}{Style.RESET_ALL}")
            print(f"Прибыль:             {Fore.CYAN}${self.metrics.profit_5min:.2f}{Style.RESET_ALL}")
            print(f"Ошибки:              {Fore.CYAN}{self.metrics.errors_5min}{Style.RESET_ALL}")
            print()
            
            # Статус за 1 час
            print(f"{Fore.YELLOW}🕐 СТАТУС ЗА 1 ЧАС:")
            print(f"Общий статус:        {self.get_1hour_status()}")
            print(f"Возможности:         {Fore.CYAN}{self.metrics.opportunities_1hour}{Style.RESET_ALL}")
            print(f"Сделки:              {Fore.CYAN}{self.metrics.trades_1hour}{Style.RESET_ALL}")
            print(f"Прибыль:             {Fore.CYAN}${self.metrics.profit_1hour:.2f}{Style.RESET_ALL}")
            print(f"Ошибки:              {Fore.CYAN}{self.metrics.errors_1hour}{Style.RESET_ALL}")
            print()
            
            # Общие метрики
            print(f"{Fore.YELLOW}🔧 ОБЩИЕ МЕТРИКИ:")
            print(f"Активных бирж:       {Fore.CYAN}{self.metrics.active_exchanges}{Style.RESET_ALL}")
            print(f"Качество данных:     {Fore.CYAN}{self.metrics.data_quality:.1f}%{Style.RESET_ALL}")
            print(f"Частота сканирования: {Fore.CYAN}{self.metrics.scan_frequency:.2f} Hz{Style.RESET_ALL}")
            print()
            
            # Время работы
            uptime = datetime.now() - self.metrics.start_time
            print(f"Время работы:        {Fore.CYAN}{str(uptime).split('.')[0]}{Style.RESET_ALL}")
            print(f"Последнее обновление: {Fore.CYAN}{self.metrics.last_update.strftime('%H:%M:%S')}{Style.RESET_ALL}")
            print()
            print(f"{Fore.WHITE}Нажмите Ctrl+C для выхода{Style.RESET_ALL}")
            
            await asyncio.sleep(2)
    
    async def run(self):
        """Запуск монитора"""
        self.running = True
        self.find_log_files()
        
        print(f"{Fore.GREEN}🚀 Performance Status Monitor запущен{Style.RESET_ALL}")
        print(f"Найдено лог файлов: {len(self.log_files)}")
        
        # Запуск задач
        tasks = [
            asyncio.create_task(self.parse_logs()),
            asyncio.create_task(self.display_dashboard())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print(f"\n{Fore.GREEN}✅ Performance Status Monitor остановлен{Style.RESET_ALL}")
        finally:
            self.running = False

async def main():
    """Главная функция"""
    monitor = PerformanceStatusMonitor()
    await monitor.run()

if __name__ == "__main__":
    asyncio.run(main())
