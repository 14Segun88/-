import json
import os
import glob
import argparse
import logging
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from datetime import datetime
from matplotlib.patches import Patch

def get_min_profit_threshold(exchange_name):
    """Загружает MIN_PROFIT_THRESHOLD из соответствующего файла конфигурации."""
    try:
        if exchange_name == 'huobi':
            from config import MIN_PROFIT_THRESHOLD
            return MIN_PROFIT_THRESHOLD
        elif exchange_name == 'binance':
            from config_binance import MIN_PROFIT_THRESHOLD
            return MIN_PROFIT_THRESHOLD
    except (ImportError, ModuleNotFoundError):
        print(f"Warning: Could not import config for {exchange_name}. Using default threshold 0.1.")
    return 0.1 # Значение по умолчанию

def generate_report(df: pd.DataFrame, filename: str, exchange_name: str):
    # --- ГЕНЕРАЦИЯ ДЕТАЛЬНОГО PNG-ОТЧЕТА ---
    # Создает комплексный визуальный отчет по результатам арбитражного анализа.
    # Args:
    #     df (pd.DataFrame): DataFrame с данными о прибыльности. 
    #                        Колонки: 'timestamp', 'profit_percentage', 'path'.
    #     filename (str): Имя файла для сохранения отчета.
    #     exchange_name (str): Название биржи для заголовков.
    """
    Генерирует детализированный отчет на основе DataFrame с данными о дивергенции.
    Для каждой арбитражной связки создается отдельный блок со статистикой и двумя графиками:
    1. Анализ прибыльности во времени (с цветными столбиками).
    2. Гистограмма распределения прибыльности.
    """
    if df.empty:
        logging.warning("DataFrame is empty. Generating an empty report.")
        fig, ax = plt.subplots(figsize=(12, 6))
        # --- ОБЩИЙ ЗАГОЛОВОК ОТЧЕТА ---
        fig.suptitle(f'Triangular Arbitrage Analysis - {exchange_name}', fontsize=16, weight='bold')
        ax.text(0.5, 0.5, 'No market divergence data was collected.',
                horizontalalignment='center', verticalalignment='center', fontsize=18, color='grey')
        ax.set_axis_off()
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        return

    # Определяем уникальные арбитражные связки (пути)
    unique_paths = df['path'].unique()
    # Ограничение на 4 связки убрано по запросу пользователя. Отчет будет сгенерирован для всех найденных путей.

    num_paths = len(unique_paths)
    if num_paths == 0: return

    min_profit_threshold = get_min_profit_threshold(exchange_name.lower())

    # --- Начало генерации отчета ---
    # Определяем количество строк для основной сетки. Каждая строка - одна арбитражная связка.
    ncols = 3  # Задаем 3 колонки для лучшей читаемости
    nrows = (num_paths + ncols - 1) // ncols
    fig = plt.figure(figsize=(25, 8 * nrows))
    fig.suptitle(f'Triangular Arbitrage Analysis - {exchange_name.capitalize()}', fontsize=22, y=0.98)
    outer_grid = gridspec.GridSpec(nrows, ncols, wspace=0.2, hspace=0.5)

    # --- Основной цикл: проходим по каждой уникальной связке и рисуем для нее блок --- 
    for i, path_name in enumerate(unique_paths):
        path_df = df[df['path'] == path_name]
        profits = path_df['profit_percentage']

        # Статистика
        opportunity_count = len(profits)
        profitable_count = (profits > 0).sum()
        win_rate = (profitable_count / opportunity_count * 100) if opportunity_count > 0 else 0
        mean_profit = profits.mean()
        
        stats_text = (
            f'--- Path: {path_name} ---\n'
            f'Total Opportunities: {opportunity_count}\n'
            f'Profitable (>0%): {profitable_count} ({win_rate:.2f}%)\n'
            f'Mean Gross Profit: {mean_profit:.4f}%'
        )

        # Создаем внутреннюю сетку для одного блока отчета
        inner_grid = gridspec.GridSpecFromSubplotSpec(3, 1, subplot_spec=outer_grid[i], hspace=0.6, height_ratios=[0.5, 2, 1])

        # 1. Блок статистики
        ax_stats = plt.Subplot(fig, inner_grid[0])
        ax_stats.text(0.5, 0.5, stats_text, ha='center', va='center', fontsize=12, 
                      bbox=dict(boxstyle='round,pad=0.5', fc='aliceblue', ec='black', lw=1))
        ax_stats.set_axis_off()
        fig.add_subplot(ax_stats)

        # 2. График прибыли по времени
        ax_ts = plt.Subplot(fig, inner_grid[1])
        # --- ЛОГИКА РАСКРАСКИ ГРАФИКА ---
        # Зеленый: Явная прибыльная возможность (>= 0.3%).
        # Желтый: Небольшая прибыль, вероятно, будет съедена непредвиденными факторами (0 < p < 0.3%).
        # Красный: Убыточная возможность.
        colors = []
        for p in profits:
            if p >= 0.3:
                colors.append('green')
            elif p > 0:
                colors.append('yellow')
            else:
                colors.append('red')
        ax_ts.bar(path_df.index, profits, color=colors, width=0.0001)
        ax_ts.axhline(0, color='black', linestyle='-', linewidth=1)
        ax_ts.axhline(min_profit_threshold, color='green', linestyle='--', linewidth=1.5)
        ax_ts.set_title('Triangular Arbitrage Analysis - Binance', fontsize=12, pad=10)
        ax_ts.set_ylabel('Net Profit (%)')
        ax_ts.grid(True, linestyle='--', alpha=0.5)
        ax_ts.tick_params(axis='x', rotation=15)
        
        # --- СОЗДАНИЕ ЛЕГЕНДЫ ДЛЯ ГРАФИКА ---
        legend_elements = [Patch(facecolor='green', edgecolor='g', label='Прибыль > 0.3%'),
                           Patch(facecolor='yellow', edgecolor='y', label='0 < Прибыль < 0.3%'),
                           Patch(facecolor='red', edgecolor='r', label='Убыток')]
        ax_ts.legend(handles=legend_elements, loc='upper left')
        fig.add_subplot(ax_ts)

        # 3. Гистограмма распределения прибыли
        ax_hist = plt.Subplot(fig, inner_grid[2])
        ax_hist.hist(profits, bins=50, color='royalblue', alpha=0.75)
        ax_hist.axvline(0, color='red', linestyle='--', linewidth=1, label='Breakeven')
        ax_hist.axvline(mean_profit, color='green', linestyle='-', linewidth=1.5, label=f'Mean: {mean_profit:.4f}%')
        ax_hist.set_title('Distribution of Arbitrage Opportunities')
        ax_hist.set_xlabel('Gross Profit (%)')
        ax_hist.set_ylabel('Frequency')
        ax_hist.legend()
        ax_hist.grid(True, linestyle='--', alpha=0.5)
        fig.add_subplot(ax_hist)

    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    logging.info(f"Detailed report saved to: {filename}")

if __name__ == '__main__':
    # Этот блок теперь предназначен для ручного тестирования генератора отчетов
    # Пример: python generate_detailed_report.py <путь_к_json_логу> <имя_выходного_файла.png> <имя_биржи>
    parser = argparse.ArgumentParser(description='Generate a detailed arbitrage report from a trade log file.')
    parser.add_argument('log_file', type=str, help='Path to the JSON trade log file.')
    parser.add_argument('output_file', type=str, help='Path to save the output PNG report.')
    parser.add_argument('exchange_name', type=str, choices=['huobi', 'binance'], help='The name of the exchange.')
    
    args = parser.parse_args()

    try:
        # Загружаем данные из JSON для тестирования
        with open(args.log_file, 'r') as f:
            trades = json.load(f)
        # Преобразуем в DataFrame, который ожидает функция
        df = pd.DataFrame(trades)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        # Для отчета нам нужна 'грязная' прибыль
        df.rename(columns={'gross_profit_pct': 'profit_percentage'}, inplace=True)
        
        print(f"Generating report from {args.log_file}...")
        generate_report(df, args.output_file, args.exchange_name)
        print(f"Report saved to {args.output_file}")

    except FileNotFoundError:
        print(f"Error: The file {args.log_file} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
