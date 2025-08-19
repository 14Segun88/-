#!/usr/bin/env python3
"""
🔍 CRITICAL SCANNER MONITOR - Real-time Critical Data Monitoring
Мониторинг критических данных сканера в реальном времени
"""

import asyncio
import aiohttp
import json
import time
import os
import sys
import re
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging
from colorama import init, Fore, Back, Style
import threading
from pathlib import Path

# Инициализация цветного вывода
init(autoreset=True)

@dataclass
class CriticalMetrics:
    """Критические метрики сканера"""
    # Качество данных
    data_latency_ms: float = 0.0
    data_freshness_pct: float = 0.0
    data_quality_score: float = 0.0
    stale_data_count: int = 0
    
    # WebSocket статус
    ws_connections: Dict[str, bool] = field(default_factory=dict)
    ws_last_message: Dict[str, float] = field(default_factory=dict)
    ws_message_rate: Dict[str, float] = field(default_factory=dict)
    
    # Ликвидность
    avg_orderbook_depth_usd: float = 0.0
    min_bid_ask_volume_usd: float = 0.0
    liquidity_impact_pct: float = 0.0
    
    # Производительность
    scan_frequency_hz: float = 0.0
    processing_time_ms: float = 0.0
    missed_scans: int = 0
    
    # Фильтрация сигналов
    total_signals: int = 0
    filtered_signals: int = 0
    quality_signals: int = 0
    false_positives: int = 0
    anomalous_spreads: int = 0
    
    # Арбитражные возможности
    inter_opportunities: int = 0
    triangular_opportunities: int = 0
    avg_profit_pct: float = 0.0
    max_profit_pct: float = 0.0
    opportunities_per_hour: float = 0.0
    
    # Ошибки и проблемы
    connection_errors: int = 0
    data_errors: int = 0
    timeout_errors: int = 0
    api_rate_limits: int = 0

@dataclass
class ExchangeCriticalData:
    """Критические данные биржи"""
    name: str
    # Подключение
    rest_connected: bool = False
    rest_latency_ms: float = 0.0
    ws_connected: bool = False
    ws_last_ping: float = 0.0
    
    # Качество данных
    data_quality: float = 0.0
    orderbook_depth_usd: float = 0.0
    active_pairs: int = 0
    volume_24h_usd: float = 0.0
    
    # Ошибки
    error_count: int = 0
    last_error: str = ""
    rate_limited: bool = False

class CriticalScannerMonitor:
    """Монитор критических данных сканера"""
    
    def __init__(self):
        self.metrics = CriticalMetrics()
        self.exchanges = {}
        self.opportunity_history = deque(maxlen=100)
        self.running = False
        self.last_update = time.time()
        self.log_files = []
        self.log_positions = {}
        
        # Инициализация счетчиков для парсинга
        self.total_scans = 0
        self.last_scan_count = 0
        self.ws_message_count = 0
        self.connected_exchanges = 0
        self.parsing_stats = False
        
        # Критические пороги для 10/10
        self.critical_thresholds = {
            'MAX_DATA_LATENCY_MS': 50,
            'MIN_DATA_FRESHNESS_PCT': 95,
            'MIN_DATA_QUALITY': 0.95,
            'MIN_WS_CONNECTIONS': 3,
            'MIN_ORDERBOOK_DEPTH_USD': 1000,
            'MIN_SCAN_FREQUENCY_HZ': 1.0,
            'MAX_PROCESSING_TIME_MS': 100,
            'MIN_SIGNAL_QUALITY_PCT': 10,
            'MAX_FALSE_POSITIVE_PCT': 5,
            'MIN_OPPORTUNITIES_PER_HOUR': 5,
            'MAX_ERROR_RATE_PCT': 2
        }
        
        # Инициализация бирж
        self.init_exchanges()
        self.find_log_files()
        
    def init_exchanges(self):
        """Инициализация данных бирж"""
        exchange_configs = {
            'mexc': 'MEXC',
            'bybit': 'Bybit', 
            'huobi': 'Huobi',
            'binance': 'Binance',
            'okx': 'OKX',
            'kucoin': 'KuCoin'
        }
        
        for exchange_id, name in exchange_configs.items():
            self.exchanges[exchange_id] = ExchangeCriticalData(name=name)
            self.metrics.ws_connections[exchange_id] = False
            self.metrics.ws_last_message[exchange_id] = 0
            self.metrics.ws_message_rate[exchange_id] = 0
    
    def find_log_files(self):
        """Поиск лог файлов бота"""
        patterns = [
            "production_bot.log",
            "websocket_bot.log", 
            "mega_arbitrage_bot.log",
            "*bot*.log",
            "*.log"
        ]
        
        for pattern in patterns:
            files = glob.glob(pattern)
            self.log_files.extend(files)
        
        # Удаление дубликатов и сортировка
        self.log_files = list(set(self.log_files))
        self.log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Инициализация позиций в файлах
        for log_file in self.log_files:
            self.log_positions[log_file] = 0
        
        if self.log_files:
            print(f"📄 Мониторинг файлов: {', '.join(self.log_files[:3])}")
    
    async def start_monitoring(self):
        """Запуск мониторинга"""
        self.running = True
        
        tasks = [
            self.monitor_exchanges(),
            self.parse_logs_realtime(),
            self.calculate_metrics(),
            self.display_critical_dashboard()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def monitor_exchanges(self):
        """Мониторинг состояния бирж"""
        exchange_urls = {
            'mexc': 'https://api.mexc.com/api/v3/ping',
            'bybit': 'https://api.bybit.com/v5/market/time',
            'huobi': 'https://api.huobi.pro/v1/common/timestamp',
            'binance': 'https://api.binance.com/api/v3/ping',
            'okx': 'https://www.okx.com/api/v5/public/time'
        }
        
        while self.running:
            for exchange_id, url in exchange_urls.items():
                try:
                    start_time = time.time()
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=5) as response:
                            latency = (time.time() - start_time) * 1000
                            
                            exchange = self.exchanges[exchange_id]
                            exchange.rest_connected = response.status == 200
                            exchange.rest_latency_ms = latency
                            exchange.data_quality = 1.0 if latency < 100 else 0.8
                            exchange.error_count = 0 if exchange.rest_connected else exchange.error_count + 1
                            
                except Exception as e:
                    if exchange_id in self.exchanges:
                        self.exchanges[exchange_id].rest_connected = False
                        self.exchanges[exchange_id].error_count += 1
                        self.exchanges[exchange_id].last_error = str(e)[:50]
                        self.metrics.connection_errors += 1
            
            await asyncio.sleep(2)
    
    async def parse_logs_realtime(self):
        """Парсинг логов в реальном времени"""
        while self.running:
            try:
                for log_file in self.log_files:
                    if not os.path.exists(log_file):
                        continue
                        
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            # Переходим к последней позиции
                            f.seek(self.log_positions[log_file])
                            new_lines = f.readlines()
                            self.log_positions[log_file] = f.tell()
                            
                            for line in new_lines:
                                await self.parse_log_line(line.strip())
                                
                    except Exception as e:
                        pass  # Игнорируем ошибки чтения файла
                        
            except Exception as e:
                pass  # Игнорируем общие ошибки
            
            await asyncio.sleep(1)
    
    async def parse_log_line(self, line: str):
        """Парсинг строки лога"""
        try:
            # Парсинг статистики работы бота
            if "СТАТИСТИКА РАБОТЫ" in line:
                self.parsing_stats = True
            elif "===============" in line and hasattr(self, 'parsing_stats'):
                self.parsing_stats = False
            elif hasattr(self, 'parsing_stats') and self.parsing_stats:
                # Парсинг сканирований
                if "Сканирований:" in line:
                    match = re.search(r'Сканирований:\s*(\d+)', line)
                    if match:
                        self.total_scans = int(match.group(1))
                        # Обновляем частоту
                        if hasattr(self, 'last_scan_count'):
                            scans_diff = self.total_scans - self.last_scan_count
                            if scans_diff > 0:
                                self.metrics.scan_frequency_hz = scans_diff  # сканов в интервал
                        self.last_scan_count = self.total_scans
                
                # Парсинг найденных возможностей  
                elif "Найдено возможностей:" in line:
                    match = re.search(r'возможностей:\s*(\d+)', line)
                    if match:
                        self.metrics.inter_opportunities = int(match.group(1))
                        self.metrics.total_signals = self.metrics.inter_opportunities
                
                # Парсинг WebSocket сообщений
                elif "WebSocket сообщений:" in line:
                    match = re.search(r'сообщений:\s*(\d+)', line)
                    if match:
                        self.ws_message_count = int(match.group(1))
                
                # Парсинг ошибок
                elif "Ошибок:" in line:
                    match = re.search(r'Ошибок:\s*(\d+)', line)
                    if match:
                        # Сбрасываем и устанавливаем реальное количество
                        self.metrics.data_errors = int(match.group(1))
                
                # Парсинг подключенных бирж
                elif "Подключено бирж:" in line:
                    match = re.search(r'бирж:\s*(\d+)', line)
                    if match:
                        self.connected_exchanges = int(match.group(1))
            
            # Парсинг WebSocket подключений из логов
            elif "WebSocket подключен" in line:
                for exchange_id in ['MEXC', 'Bybit', 'Huobi', 'Binance', 'OKX', 'KuCoin', 'Kraken']:
                    if exchange_id in line:
                        self.metrics.ws_connections[exchange_id.lower()] = True
                        self.metrics.ws_last_message[exchange_id.lower()] = time.time()
            
            # Парсинг WebSocket подписок
            elif "подписался на" in line:
                for exchange_id in ['MEXC', 'Bybit', 'Huobi', 'Binance', 'OKX', 'KuCoin', 'Kraken']:
                    if exchange_id in line:
                        match = re.search(r'(\d+)\s+(пар|канал|поток|топик)', line)
                        if match:
                            pairs_count = int(match.group(1))
                            if exchange_id.lower() in self.exchanges:
                                self.exchanges[exchange_id.lower()].active_pairs = pairs_count
            
            # Парсинг возможностей арбитража
            elif "Чистая прибыль:" in line:
                profit_match = re.search(r'(\d+\.?\d*)%', line)
                if profit_match:
                    profit_pct = float(profit_match.group(1))
                    self.metrics.total_signals += 1
                    
                    if profit_pct > 3.0:  # Аномальный спред
                        self.metrics.anomalous_spreads += 1
                        self.metrics.filtered_signals += 1
                    elif profit_pct < 0.05:  # Слишком маленькая прибыль
                        self.metrics.filtered_signals += 1
                    else:
                        self.metrics.quality_signals += 1
                        self.metrics.avg_profit_pct = (self.metrics.avg_profit_pct + profit_pct) / 2
                        self.metrics.max_profit_pct = max(self.metrics.max_profit_pct, profit_pct)
            
            # НЕ увеличиваем счетчик ошибок при каждом упоминании слова "ошибка"
            # Используем только реальное количество из статистики
                
        except Exception as e:
            pass  # Не увеличиваем счетчик при ошибках парсинга
    
    async def calculate_metrics(self):
        """Расчет метрик"""
        while self.running:
            try:
                # Расчет качества данных
                connected_exchanges = sum(1 for ex in self.exchanges.values() if ex.rest_connected)
                if connected_exchanges > 0:
                    avg_quality = sum(ex.data_quality for ex in self.exchanges.values() if ex.rest_connected) / connected_exchanges
                    self.metrics.data_quality_score = avg_quality
                
                # Расчет латентности
                latencies = [ex.rest_latency_ms for ex in self.exchanges.values() if ex.rest_connected]
                if latencies:
                    self.metrics.data_latency_ms = sum(latencies) / len(latencies)
                
                # Расчет свежести данных
                total_data_points = self.metrics.total_signals + self.metrics.stale_data_count
                if total_data_points > 0:
                    self.metrics.data_freshness_pct = (
                        (total_data_points - self.metrics.stale_data_count) / total_data_points * 100
                    )
                
                # Расчет возможностей в час
                current_time = time.time()
                if hasattr(self, 'start_time'):
                    hours_running = (current_time - self.start_time) / 3600
                    if hours_running > 0:
                        self.metrics.opportunities_per_hour = self.metrics.inter_opportunities / hours_running
                else:
                    self.start_time = current_time
                
                self.last_update = time.time()
                
            except Exception as e:
                pass  # Не увеличиваем счетчик ошибок
            
            await asyncio.sleep(5)
    
    def get_status_indicator(self, value, threshold, reverse=False, percentage=False):
        """Получить индикатор статуса"""
        if percentage:
            display_value = f"{value:.1f}%"
        else:
            display_value = f"{value:.1f}" if isinstance(value, float) else str(value)
        
        if reverse:
            status = "✅" if value <= threshold else "❌"
            color = Fore.GREEN if value <= threshold else Fore.RED
        else:
            status = "✅" if value >= threshold else "❌"
            color = Fore.GREEN if value >= threshold else Fore.RED
        
        return f"{color}{display_value} {status}{Style.RESET_ALL}"
    
    async def display_critical_dashboard(self):
        """Отображение критического дашборда"""
        while self.running:
            os.system('clear' if os.name == 'posix' else 'cls')
            
            print(f"{Fore.CYAN}{'='*90}")
            print(f"{Fore.CYAN}🔍 CRITICAL SCANNER MONITOR - Real-time Critical Data")
            print(f"{Fore.CYAN}{'='*90}")
            print(f"{Fore.WHITE}Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            # Критические параметры качества данных
            print(f"{Fore.YELLOW}📊 КАЧЕСТВО ДАННЫХ (КРИТИЧНО):")
            print(f"Средняя латентность:     {self.get_status_indicator(self.metrics.data_latency_ms, self.critical_thresholds['MAX_DATA_LATENCY_MS'], reverse=True)}ms")
            print(f"Свежесть данных:         {self.get_status_indicator(self.metrics.data_freshness_pct, self.critical_thresholds['MIN_DATA_FRESHNESS_PCT'], percentage=True)}")
            print(f"Качество данных:         {self.get_status_indicator(self.metrics.data_quality_score * 100, self.critical_thresholds['MIN_DATA_QUALITY'] * 100, percentage=True)}")
            print(f"Устаревших данных:       {Fore.CYAN}{self.metrics.stale_data_count}{Style.RESET_ALL}")
            print()
            
            # WebSocket соединения
            print(f"{Fore.YELLOW}🌐 WEBSOCKET СОЕДИНЕНИЯ:")
            ws_connected = sum(1 for connected in self.metrics.ws_connections.values() if connected)
            print(f"Активных соединений:     {self.get_status_indicator(ws_connected, self.critical_thresholds['MIN_WS_CONNECTIONS'])}")
            
            for exchange_id, connected in self.metrics.ws_connections.items():
                status_color = Fore.GREEN if connected else Fore.RED
                status_text = "✅ Connected" if connected else "❌ Disconnected"
                last_msg = self.metrics.ws_last_message.get(exchange_id, 0)
                age = time.time() - last_msg if last_msg > 0 else 999
                
                print(f"{self.exchanges[exchange_id].name:<10} {status_color}{status_text:<15}{Style.RESET_ALL} "
                      f"Last: {age:.1f}s ago")
            print()
            
            # Производительность сканера
            print(f"{Fore.YELLOW}⚡ ПРОИЗВОДИТЕЛЬНОСТЬ СКАНЕРА:")
            print(f"Частота сканирования:    {self.get_status_indicator(self.metrics.scan_frequency_hz, self.critical_thresholds['MIN_SCAN_FREQUENCY_HZ'])} Hz")
            print(f"Время обработки:         {self.get_status_indicator(self.metrics.processing_time_ms, self.critical_thresholds['MAX_PROCESSING_TIME_MS'], reverse=True)}ms")
            print(f"Пропущенных сканов:      {Fore.CYAN}{self.metrics.missed_scans}{Style.RESET_ALL}")
            print()
            
            # Ликвидность и стаканы
            print(f"{Fore.YELLOW}💰 ЛИКВИДНОСТЬ:")
            print(f"Средняя глубина стакана: {self.get_status_indicator(self.metrics.avg_orderbook_depth_usd, self.critical_thresholds['MIN_ORDERBOOK_DEPTH_USD'])} USD")
            print(f"Мин. объем bid/ask:      {Fore.CYAN}{self.metrics.min_bid_ask_volume_usd:.0f}{Style.RESET_ALL} USD")
            print(f"Влияние на цену:         {Fore.CYAN}{self.metrics.liquidity_impact_pct:.2f}%{Style.RESET_ALL}")
            print()
            
            # Фильтрация сигналов
            print(f"{Fore.YELLOW}🔍 ФИЛЬТРАЦИЯ СИГНАЛОВ:")
            print(f"Всего сигналов:          {Fore.CYAN}{self.metrics.total_signals}{Style.RESET_ALL}")
            print(f"Качественных:            {Fore.GREEN}{self.metrics.quality_signals}{Style.RESET_ALL} ({self.metrics.quality_signals/max(1,self.metrics.total_signals)*100:.1f}%)")
            print(f"Отфильтровано:           {Fore.YELLOW}{self.metrics.filtered_signals}{Style.RESET_ALL} ({self.metrics.filtered_signals/max(1,self.metrics.total_signals)*100:.1f}%)")
            print(f"Аномальных спредов:      {Fore.RED}{self.metrics.anomalous_spreads}{Style.RESET_ALL}")
            print()
            
            # Арбитражные возможности
            print(f"{Fore.YELLOW}💎 АРБИТРАЖНЫЕ ВОЗМОЖНОСТИ:")
            print(f"Межбиржевой арбитраж:    {Fore.GREEN}{self.metrics.inter_opportunities}{Style.RESET_ALL}")
            print(f"Треугольный арбитраж:    {Fore.GREEN}{self.metrics.triangular_opportunities}{Style.RESET_ALL}")
            print(f"Возможностей в час:      {self.get_status_indicator(self.metrics.opportunities_per_hour, self.critical_thresholds['MIN_OPPORTUNITIES_PER_HOUR'])}")
            print(f"Средняя прибыль:         {Fore.CYAN}{self.metrics.avg_profit_pct:.2f}%{Style.RESET_ALL}")
            print(f"Максимальная прибыль:    {Fore.CYAN}{self.metrics.max_profit_pct:.2f}%{Style.RESET_ALL}")
            print()
            
            # Ошибки и проблемы
            print(f"{Fore.YELLOW}🚨 ОШИБКИ И ПРОБЛЕМЫ:")
            total_errors = self.metrics.connection_errors + self.metrics.data_errors + self.metrics.timeout_errors
            # Правильный расчет процента: ошибки от общего числа операций
            total_operations = getattr(self, 'total_scans', 1) + self.metrics.total_signals
            error_rate = (total_errors / max(1, total_operations)) * 100
            print(f"Общий процент ошибок:    {self.get_status_indicator(error_rate, self.critical_thresholds['MAX_ERROR_RATE_PCT'], reverse=True, percentage=True)}")
            print(f"Ошибки подключения:      {Fore.RED}{self.metrics.connection_errors}{Style.RESET_ALL}")
            print(f"Ошибки данных:           {Fore.RED}{self.metrics.data_errors}{Style.RESET_ALL}")
            print(f"Таймауты:                {Fore.RED}{self.metrics.timeout_errors}{Style.RESET_ALL}")
            print(f"Rate limits:             {Fore.YELLOW}{self.metrics.api_rate_limits}{Style.RESET_ALL}")
            print()
            
            # Статус бирж детально
            print(f"{Fore.YELLOW}📡 ДЕТАЛЬНЫЙ СТАТУС БИРЖ:")
            print(f"{'Биржа':<10} {'REST':<12} {'WebSocket':<12} {'Глубина':<10} {'Ошибки':<8}")
            print("-" * 70)
            
            for exchange_id, exchange in self.exchanges.items():
                rest_status = f"✅ {exchange.rest_latency_ms:.0f}ms" if exchange.rest_connected else "❌ Offline"
                ws_status = "✅ Active" if self.metrics.ws_connections.get(exchange_id, False) else "❌ Down"
                depth = f"${exchange.orderbook_depth_usd:.0f}" if exchange.orderbook_depth_usd > 0 else "$0"
                
                rest_color = Fore.GREEN if exchange.rest_connected else Fore.RED
                ws_color = Fore.GREEN if self.metrics.ws_connections.get(exchange_id, False) else Fore.RED
                
                print(f"{exchange.name:<10} {rest_color}{rest_status:<12}{Style.RESET_ALL} "
                      f"{ws_color}{ws_status:<12}{Style.RESET_ALL} {depth:<10} {exchange.error_count:<8}")
            
            print()
            print(f"{Fore.WHITE}Последнее обновление: {datetime.fromtimestamp(self.last_update).strftime('%H:%M:%S')}")
            print(f"{Fore.WHITE}Нажмите Ctrl+C для выхода")
            
            await asyncio.sleep(1)

async def main():
    """Главная функция"""
    monitor = CriticalScannerMonitor()
    
    try:
        print(f"{Fore.CYAN}🚀 Запуск Critical Scanner Monitor...")
        print(f"{Fore.WHITE}Мониторинг критических параметров сканера...")
        await asyncio.sleep(2)
        
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️ Остановка мониторинга...")
        monitor.running = False
    except Exception as e:
        print(f"\n{Fore.RED}❌ Ошибка: {e}")
    finally:
        print(f"{Fore.GREEN}✅ Critical Scanner Monitor остановлен")

if __name__ == "__main__":
    # Установка зависимостей
    try:
        import colorama, aiohttp
    except ImportError:
        print("📥 Установка зависимостей...")
        os.system("pip install colorama aiohttp")
    
    asyncio.run(main())
