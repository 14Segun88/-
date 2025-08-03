import ccxt
import time
import json
import pandas as pd
import matplotlib.pyplot as plt
import logging
from arbitrage_strategy import TriangularArbitrageStrategy
import config

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def plot_histogram(data):
    if not data:
        print("Не удалось собрать данные для анализа.")
        return

    df = pd.DataFrame(data)
    plt.figure(figsize=(10, 6))
    plt.hist(df['profit_percent'], bins=100, alpha=0.75)
    plt.title('Распределение арбитражных расхождений')
    plt.xlabel('Процент расхождения (%)')
    plt.ylabel('Частота')
    plt.grid(True)
    plt.show()

def main():
    # Инициализация биржи
    # Для спотового рынка Huobi (HTX) используйте 'htx'
    exchange = ccxt.htx({
        'options': {
            'defaultType': 'spot', # Указываем спотовый рынок
        },
        'enableRateLimit': True,
    })

    strategy = TriangularArbitrageStrategy(
        symbols=config.SYMBOLS,
        min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
        position_size=config.POSITION_SIZE,
        fee_rate=config.FEE_RATE
    )
    collected_divergence = []

    print("Робот запущен. Начинаем сбор данных...")
    print(f"Торговые пары: {config.SYMBOLS}")
    print("Нажмите Ctrl+C для завершения.")

    try:
        while True:
            try:
                # Получаем последние цены для всех символов одним запросом
                tickers = exchange.fetch_tickers(config.SYMBOLS)
                
                # Обновляем данные в стратегии
                for symbol, ticker_data in tickers.items():
                    # Проверяем, что данные по тикеру не пустые
                    if ticker_data and ticker_data['bid'] is not None and ticker_data['ask'] is not None:
                        market_data = {
                            'bid': ticker_data['bid'],
                            'ask': ticker_data['ask']
                        }
                        strategy.update_market_data(symbol, market_data)

                # Рассчитываем расхождение
                divergence_result = strategy.calculate_divergence()
                if divergence_result:
                    collected_divergence.append(divergence_result)
                    print(f"[Collector] Расхождение: {divergence_result['profit_percent']:.4f}% для пути {divergence_result['path_name']}")

                # Проверяем на арбитраж
                arbitrage_opportunity = strategy.calculate_arbitrage()
                if arbitrage_opportunity:
                    print(f"\033[92m[ARBITRAGE DETECTED] {arbitrage_opportunity}\033[0m")

            except ccxt.NetworkError as e:
                logging.error(f"Ошибка сети: {e}. Повторная попытка через 5 секунд...")
                time.sleep(5)
            except ccxt.ExchangeError as e:
                logging.error(f"Ошибка биржи: {e}. Повторная попытка через 20 секунд...")
                time.sleep(20)
            except Exception as e:
                logging.error(f"Непредвиденная ошибка: {e}")
                time.sleep(10)

            # Пауза между запросами, чтобы не превышать лимиты API
            time.sleep(config.COLLECTOR_INTERVAL)

    except KeyboardInterrupt:
        print("\nЗавершение работы по команде пользователя...")
    finally:
        if collected_divergence:
            with open('live_divergence_data.json', 'w') as f:
                json.dump(collected_divergence, f, indent=4)
            print(f"Собранные данные сохранены в live_divergence_data.json ({len(collected_divergence)} записей)")
            plot_histogram(collected_divergence)
        else:
            print("Не удалось собрать данные для анализа.")
        print("Программа завершена.")

if __name__ == "__main__":
    main()