#!/usr/bin/env python3
"""
Real-Time Trader Monitor - 100% точный мониторинг трейдера без фейков
Читает реальные данные о торговле из логов
"""

import asyncio
import os
import re
import json
from datetime import datetime, timedelta
from collections import deque
import time

# ANSI цвета
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class RealTraderMonitor:
    def __init__(self):
        self.log_file = 'production_bot.log'  # Читаем логи от production_multi_exchange_bot.py
        self.log_position = 0
        self.start_time = datetime.now()
        
        # Метрики трейдера
        self.metrics = {
            'opportunities_checked': 0,
            'opportunities_validated': 0,
            'orders_placed': 0,
            'orders_filled': 0,
            'orders_failed': 0,
            'total_volume': 0.0,
            'total_profit': 0.0,
            'fill_rate': 0.0,
            'avg_fill_time': 0.0,
            'last_update': None
        }
        
        # ПРОФЕССИОНАЛЬНЫЕ ПОРОГИ КАЧЕСТВА 10/10 для REAL TRADER MONITOR
        self.quality_thresholds = {
            'MIN_WIN_RATE': 80.0,           # ≥80% успешных сделок - КЛАСС 10/10
            'MIN_PROFIT_FACTOR': 2.5,       # ≥2.5 коэффициент прибыли - ЭЛИТНЫЙ
            'MAX_DRAWDOWN': 2.5,            # ≤2.5% максимальная просадка - ПРЕМИУМ
            'MIN_MONTHLY_RETURN': 15.0,     # ≥15% месячная доходность - ТОПОВЫЙ
            'MAX_RISK_PER_TRADE': 1.0,      # ≤1.0% риска на сделку - КОНСЕРВАТИВНЫЙ
            'MIN_SHARP_RATIO': 2.0,         # ≥2.0 коэффициент Шарпа - ОТЛИЧНЫЙ
            'MAX_ORDER_LATENCY': 50,        # ≤50мс средняя латентность - МОЛНИЕНОСНО
            'MIN_FILL_RATE': 99.0,          # ≥99% исполнение ордеров - БЕЗУПРЕЧНО
            'MIN_OPPORTUNITIES_PER_HOUR': 20, # ≥20 возможностей в час - АКТИВНЫЙ ПОИСК
            'MAX_ERROR_RATE': 0.2           # ≤0.2% ошибок системы - НАДЕЖНОСТЬ 10/10
        }
        
        # Балансы бирж
        self.balances = {}
        
        # История для анализа
        self.fill_times = deque(maxlen=100)
        self.profits = deque(maxlen=100)
        self.spreads = deque(maxlen=100)
        
    async def read_logs(self):
        """Читает логи в реальном времени"""
        while True:
            try:
                if not os.path.exists(self.log_file):
                    await asyncio.sleep(1)
                    continue
                
                with open(self.log_file, 'r') as f:
                    f.seek(self.log_position)
                    new_lines = f.readlines()
                    self.log_position = f.tell()
                
                for line in new_lines:
                    self.parse_line(line)
                
                await asyncio.sleep(0.5)
                
            except Exception:
                await asyncio.sleep(1)
    
    def parse_line(self, line):
        """Парсит строку лога"""
        try:
            self.metrics['last_update'] = datetime.now()
            
            # Возможности арбитража из production_multi_exchange_bot.py
            if '💎 Найдена возможность:' in line:
                self.metrics['opportunities_checked'] += 1
                
                # Извлекаем прибыль
                profit_match = re.search(r'Прибыль: ([0-9.]+)%', line)
                if profit_match:
                    profit = float(profit_match.group(1))
                    self.spreads.append(profit)
            
            # Валидация возможностей
            if '✅ Сделка исполнена успешно' in line:
                self.metrics['opportunities_validated'] += 1
            
            # Размещение ордеров
            if '💼 Исполнено сделок:' in line:
                trades_match = re.search(r'💼 Исполнено сделок: ([0-9]+)', line)
                if trades_match:
                    self.metrics['orders_placed'] = int(trades_match.group(1))
            
            # Исполнение ордеров
            if '✅ Сделка исполнена успешно' in line:
                self.metrics['orders_filled'] += 1
            
            # Неудачные ордера
            if '❌ Сделка не исполнена' in line:
                self.metrics['orders_failed'] += 1
            
            # Статистика прибыли
            if '💰 Прибыль: $' in line:
                profit_match = re.search(r'💰 Прибыль: \$([0-9.]+)', line)
                if profit_match:
                    self.metrics['total_profit'] = float(profit_match.group(1))
                    if self.metrics['total_profit'] > 0:
                        self.profits.append(self.metrics['total_profit'])
            
            # Статистика объема
            if '📦 Объем торгов: $' in line:
                volume_match = re.search(r'📦 Объем торгов: \$([0-9.]+)', line)
                if volume_match:
                    self.metrics['total_volume'] = float(volume_match.group(1))
            
            # Пропущенные возможности
            if 'Opportunity skipped' in line:
                pass  # Возможность проверена, но не валидирована
                
        except Exception:
            pass
    
    def calculate_metrics(self):
        """Рассчитывает производные метрики"""
        # Fill rate
        if self.metrics['orders_placed'] > 0:
            self.metrics['fill_rate'] = (self.metrics['orders_filled'] / self.metrics['orders_placed']) * 100
        
        # Среднее время исполнения
        if self.fill_times:
            self.metrics['avg_fill_time'] = sum(self.fill_times) / len(self.fill_times)
    
    def get_status_color(self, value, good, bad, reverse=False):
        """Определяет цвет по значению"""
        if reverse:
            if value <= good:
                return Colors.GREEN
            elif value <= bad:
                return Colors.YELLOW
            else:
                return Colors.RED
        else:
            if value >= good:
                return Colors.GREEN
            elif value >= bad:
                return Colors.YELLOW
            else:
                return Colors.RED
    
    def format_uptime(self):
        """Форматирует время работы"""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        seconds = int(uptime.total_seconds() % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    async def display_dashboard(self):
        """Отображает дашборд трейдера"""
        while True:
            self.calculate_metrics()
            
            # Очищаем экран
            print('\033[2J\033[H', end='')
            
            # Заголовок
            print(f"{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════╗{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}║         REAL-TIME TRADER MONITOR (NO FAKE DATA)         ║{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════╝{Colors.RESET}")
            print()
            
            # Основные метрики
            print(f"{Colors.BOLD}💼 ТОРГОВАЯ АКТИВНОСТЬ:{Colors.RESET}")
            print(f"├─ Время работы: {Colors.CYAN}{self.format_uptime()}{Colors.RESET}")
            print(f"├─ Проверено возможностей: {Colors.CYAN}{self.metrics['opportunities_checked']}{Colors.RESET}")
            print(f"├─ Валидировано: {Colors.GREEN}{self.metrics['opportunities_validated']}{Colors.RESET}")
            
            validation_rate = 0
            if self.metrics['opportunities_checked'] > 0:
                validation_rate = (self.metrics['opportunities_validated'] / self.metrics['opportunities_checked']) * 100
            val_color = self.get_status_color(validation_rate, 50, 30)
            print(f"└─ Процент валидации: {val_color}{validation_rate:.1f}%{Colors.RESET}")
            print()
            
            # Ордера
            print(f"{Colors.BOLD}📋 ИСПОЛНЕНИЕ ОРДЕРОВ:{Colors.RESET}")
            print(f"├─ Размещено: {Colors.CYAN}{self.metrics['orders_placed']}{Colors.RESET}")
            print(f"├─ Исполнено: {Colors.GREEN}{self.metrics['orders_filled']}{Colors.RESET}")
            print(f"├─ Неудачно: {Colors.RED}{self.metrics['orders_failed']}{Colors.RESET}")
            
            fill_color = self.get_status_color(self.metrics['fill_rate'], 90, 70)
            print(f"├─ Fill Rate: {fill_color}{self.metrics['fill_rate']:.1f}%{Colors.RESET}")
            
            time_color = self.get_status_color(self.metrics['avg_fill_time'], 500, 1000, reverse=True)
            print(f"└─ Среднее время: {time_color}{self.metrics['avg_fill_time']:.0f}ms{Colors.RESET}")
            print()
            
            # Финансовые показатели
            print(f"{Colors.BOLD}💰 ФИНАНСОВЫЕ РЕЗУЛЬТАТЫ:{Colors.RESET}")
            print(f"├─ Общий объем: {Colors.CYAN}${self.metrics['total_volume']:.2f}{Colors.RESET}")
            print(f"├─ Общая прибыль: {Colors.GREEN}${self.metrics['total_profit']:.2f}{Colors.RESET}")
            
            if self.metrics['total_volume'] > 0:
                roi = (self.metrics['total_profit'] / self.metrics['total_volume']) * 100
                roi_color = self.get_status_color(roi, 0.5, 0.2)
                print(f"├─ ROI: {roi_color}{roi:.2f}%{Colors.RESET}")
            
            if self.profits:
                avg_profit = sum(self.profits) / len(self.profits)
                max_profit = max(self.profits)
                print(f"├─ Средняя прибыль: {Colors.CYAN}${avg_profit:.2f}{Colors.RESET}")
                print(f"└─ Макс. прибыль: {Colors.CYAN}${max_profit:.2f}{Colors.RESET}")
            print()
            
            # Балансы бирж
            if self.balances:
                print(f"{Colors.BOLD}💳 БАЛАНСЫ БИРЖ:{Colors.RESET}")
                total_balance = 0
                for exchange, balance in self.balances.items():
                    total_balance += balance
                    if balance > 100:
                        bal_color = Colors.GREEN
                    elif balance > 50:
                        bal_color = Colors.YELLOW
                    else:
                        bal_color = Colors.RED
                    print(f"├─ {exchange:8s}: {bal_color}${balance:.2f}{Colors.RESET}")
                print(f"└─ Всего: {Colors.CYAN}${total_balance:.2f}{Colors.RESET}")
                print()
            
            # Анализ спредов
            if self.spreads:
                print(f"{Colors.BOLD}📊 АНАЛИЗ СПРЕДОВ:{Colors.RESET}")
                avg_spread = sum(self.spreads) / len(self.spreads)
                max_spread = max(self.spreads)
                min_spread = min(self.spreads)
                print(f"├─ Средний: {Colors.CYAN}{avg_spread:.2f}%{Colors.RESET}")
                print(f"├─ Максимальный: {Colors.CYAN}{max_spread:.2f}%{Colors.RESET}")
                print(f"└─ Минимальный: {Colors.CYAN}{min_spread:.2f}%{Colors.RESET}")
                print()
            
            print(f"{Colors.CYAN}{'─' * 60}{Colors.RESET}")
            
            # Статус обновления
            if self.metrics['last_update']:
                age = (datetime.now() - self.metrics['last_update']).total_seconds()
                if age < 5:
                    update_color = Colors.GREEN
                elif age < 30:
                    update_color = Colors.YELLOW
                else:
                    update_color = Colors.RED
                print(f"Последнее обновление: {update_color}{age:.1f}s назад{Colors.RESET}")
            else:
                print(f"Последнее обновление: {Colors.YELLOW}Ожидание данных...{Colors.RESET}")
            
            await asyncio.sleep(1)
    
    async def run(self):
        """Запуск монитора"""
        tasks = [
            asyncio.create_task(self.read_logs()),
            asyncio.create_task(self.display_dashboard())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Монитор остановлен{Colors.RESET}")

async def main():
    monitor = RealTraderMonitor()
    await monitor.run()

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход...")
