import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Отключаем UserWarning от matplotlib, который вы видели ранее
import warnings
warnings.filterwarnings("ignore", category=UserWarning)


def analyze_divergence_data(filepath='live_divergence_data.json'):
    """
    Загружает, анализирует и визуализирует данные о расхождениях из JSON-файла.
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Ошибка: Файл '{filepath}' не найден. Сначала запустите main.py, чтобы собрать данные.")
        return
    except json.JSONDecodeError:
        print(f"Ошибка: Файл '{filepath}' поврежден или пуст.")
        return

    if not data:
        print("Файл с данными пуст. Анализ невозможен.")
        return

    # Преобразуем данные в DataFrame для удобного анализа
    df = pd.DataFrame(data)

    print("--- ОБЩАЯ СТАТИСТИКА ---")
    print(f"Всего записей: {len(df)}")
    
    # Общая статистика по проценту расхождения
    print("\nСтатистика по 'profit_percent':")
    print(df['profit_percent'].describe())

    print("\n--- СТАТИСТИКА ПО КАЖДОМУ ПУТИ ---")
    # Группируем данные по каждому арбитражному пути и считаем статистику
    path_stats = df.groupby('path_name')['profit_percent'].describe()
    print(path_stats)

    # --- ВИЗУАЛИЗАЦИЯ ---
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.figure(figsize=(14, 8))

    # Гистограмма распределения
    plt.hist(df['profit_percent'], bins=100, alpha=0.7, label='Все пути', color='royalblue')

    # Добавим вертикальные линии для среднего значения и нуля
    overall_mean = df['profit_percent'].mean()
    plt.axvline(overall_mean, color='red', linestyle='--', linewidth=2, label=f'Среднее: {overall_mean:.4f}%')
    plt.axvline(0, color='black', linestyle='-', linewidth=1, label='Точка безубыточности')

    plt.title('Гистограмма распределения арбитражных расхождений', fontsize=16)
    plt.xlabel('Процент расхождения (%)', fontsize=12)
    plt.ylabel('Частота', fontsize=12)
    plt.legend()
    plt.grid(True)

    # Сохраняем график в файл
    # Создаем уникальное имя файла с временной меткой
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f'divergence_histogram_{timestamp}.png'
    plt.savefig(output_filename)

    print(f"\nАнализ завершен. Гистограмма сохранена в файл: {output_filename}")

if __name__ == '__main__':
    analyze_divergence_data()
