#!/usr/bin/env python3
"""
Скрипт для сравнения результатов ботов на Huobi и Binance
"""

import os
import re
import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

def analyze_exchange_logs(log_directory, exchange_name):
    """Анализирует логи одной биржи"""
    results = {
        'exchange': exchange_name,
        'total_trades': 0,
        'successful_trades': 0,
        'failed_trades': 0,
        'total_profit_usd': 0.0,
        'profits': [],
        'timestamps': []
    }
    
    if not os.path.exists(log_directory):
        print(f"Directory {log_directory} not found")
        return results
    
    # Находим все лог файлы
    log_files = [f for f in os.listdir(log_directory) if f.endswith('.log')]
    
    for log_file in log_files:
        log_path = os.path.join(log_directory, log_file)
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Ищем результаты торговли
                if 'TRADE RESULT:' in line:
                    results['total_trades'] += 1
                    
                    # Извлекаем прибыль
                    profit_match = re.search(r'Net profit: ([+-]?\d+\.?\d*)%', line)
                    if profit_match:
                        profit_pct = float(profit_match.group(1))
                        profit_usd = (profit_pct / 100) * 15  # Предполагаем $15 позицию
                        results['profits'].append(profit_pct)
                        results['total_profit_usd'] += profit_usd
                        
                        if profit_pct > 0:
                            results['successful_trades'] += 1
                        else:
                            results['failed_trades'] += 1
                    
                    # Извлекаем временную метку
                    timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if timestamp_match:
                        results['timestamps'].append(timestamp_match.group(1))
    
    return results

def compare_exchanges():
    """Сравнивает результаты двух бирж"""
    print("="*80)
    print("🔄 СРАВНЕНИЕ РЕЗУЛЬТАТОВ HUOBI vs BINANCE")
    print("="*80)
    
    # Анализируем Huobi
    huobi_results = analyze_exchange_logs('res', 'Huobi')
    
    # Анализируем Binance
    binance_results = analyze_exchange_logs('res_binance', 'Binance')
    
    # Выводим сравнительную таблицу
    print(f"\n📊 СРАВНИТЕЛЬНАЯ ТАБЛИЦА:")
    print(f"{'Метрика':<25} {'Huobi':<15} {'Binance':<15} {'Разница':<15}")
    print("-" * 70)
    
    # Общее количество сделок
    print(f"{'Всего сделок':<25} {huobi_results['total_trades']:<15} {binance_results['total_trades']:<15} {binance_results['total_trades'] - huobi_results['total_trades']:+<15}")
    
    # Успешные сделки
    huobi_success_rate = (huobi_results['successful_trades'] / max(huobi_results['total_trades'], 1)) * 100
    binance_success_rate = (binance_results['successful_trades'] / max(binance_results['total_trades'], 1)) * 100
    print(f"{'Успешных сделок':<25} {huobi_results['successful_trades']:<15} {binance_results['successful_trades']:<15} {binance_results['successful_trades'] - huobi_results['successful_trades']:+<15}")
    print(f"{'Процент успеха':<25} {huobi_success_rate:.1f}%{'':<10} {binance_success_rate:.1f}%{'':<10} {binance_success_rate - huobi_success_rate:+.1f}%{'':<10}")
    
    # Общая прибыль
    print(f"{'Общая прибыль USD':<25} ${huobi_results['total_profit_usd']:.4f}{'':<8} ${binance_results['total_profit_usd']:.4f}{'':<8} ${binance_results['total_profit_usd'] - huobi_results['total_profit_usd']:+.4f}{'':<8}")
    
    # Средняя прибыль за сделку
    huobi_avg = np.mean(huobi_results['profits']) if huobi_results['profits'] else 0
    binance_avg = np.mean(binance_results['profits']) if binance_results['profits'] else 0
    print(f"{'Средняя прибыль %':<25} {huobi_avg:.4f}%{'':<9} {binance_avg:.4f}%{'':<9} {binance_avg - huobi_avg:+.4f}%{'':<9}")
    
    # Комиссии
    print(f"{'Комиссия за сделку':<25} {'~0.225%':<15} {'~0.075%':<15} {'-0.15%':<15}")
    
    print("\n" + "="*80)
    
    # Выводы
    print("🎯 ВЫВОДЫ:")
    if binance_results['total_profit_usd'] > huobi_results['total_profit_usd']:
        diff = binance_results['total_profit_usd'] - huobi_results['total_profit_usd']
        print(f"✅ Binance показал лучший результат на ${diff:.4f}")
    elif huobi_results['total_profit_usd'] > binance_results['total_profit_usd']:
        diff = huobi_results['total_profit_usd'] - binance_results['total_profit_usd']
        print(f"✅ Huobi показал лучший результат на ${diff:.4f}")
    else:
        print("⚖️ Результаты примерно одинаковые")
    
    print(f"📈 Разница в проценте успеха: {binance_success_rate - huobi_success_rate:+.1f}%")
    print(f"💰 Экономия на комиссиях с Binance: ~0.15% за сделку")
    
    # Создаем сравнительный график
    create_comparison_chart(huobi_results, binance_results)
    
    return huobi_results, binance_results

def create_comparison_chart(huobi_results, binance_results):
    """Создает сравнительный график"""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
    
    # График 1: Сравнение общей прибыли
    exchanges = ['Huobi', 'Binance']
    profits = [huobi_results['total_profit_usd'], binance_results['total_profit_usd']]
    colors = ['red' if p < 0 else 'green' for p in profits]
    
    ax1.bar(exchanges, profits, color=colors, alpha=0.7)
    ax1.set_title('Общая прибыль (USD)')
    ax1.set_ylabel('Прибыль ($)')
    ax1.grid(True, alpha=0.3)
    
    # График 2: Сравнение процента успеха
    success_rates = [
        (huobi_results['successful_trades'] / max(huobi_results['total_trades'], 1)) * 100,
        (binance_results['successful_trades'] / max(binance_results['total_trades'], 1)) * 100
    ]
    
    ax2.bar(exchanges, success_rates, color=['orange', 'blue'], alpha=0.7)
    ax2.set_title('Процент успешных сделок')
    ax2.set_ylabel('Успех (%)')
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)
    
    # График 3: Количество сделок
    total_trades = [huobi_results['total_trades'], binance_results['total_trades']]
    ax3.bar(exchanges, total_trades, color=['purple', 'cyan'], alpha=0.7)
    ax3.set_title('Общее количество сделок')
    ax3.set_ylabel('Количество')
    ax3.grid(True, alpha=0.3)
    
    # График 4: Средняя прибыль за сделку
    avg_profits = [
        np.mean(huobi_results['profits']) if huobi_results['profits'] else 0,
        np.mean(binance_results['profits']) if binance_results['profits'] else 0
    ]
    colors = ['red' if p < 0 else 'green' for p in avg_profits]
    
    ax4.bar(exchanges, avg_profits, color=colors, alpha=0.7)
    ax4.set_title('Средняя прибыль за сделку (%)')
    ax4.set_ylabel('Прибыль (%)')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Сохраняем график
    comparison_filename = f"exchange_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(comparison_filename, dpi=300, bbox_inches='tight')
    print(f"\n📊 Сравнительный график сохранен: {comparison_filename}")
    plt.close()

if __name__ == "__main__":
    compare_exchanges()
