#!/usr/bin/env python3
"""
🚀 PRODUCTION MULTI-EXCHANGE ARBITRAGE BOT
Профессиональный арбитражный бот для 7 бирж
Версия: 1.0.0
"""

import asyncio
import logging
import signal
import sys
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Set
from collections import defaultdict
import aiohttp

from production_config import (
    EXCHANGES_CONFIG, API_KEYS, TRADING_CONFIG, 
    WEBSOCKET_CONFIG, DYNAMIC_PAIRS_CONFIG,
    RISK_MANAGEMENT, LOGGING_CONFIG
)
from websocket_manager import WebSocketManager, OrderBook
from trading_engine import TradingEngine, ArbitrageOpportunity

# Настройка логирования
logging.basicConfig(
    level=LOGGING_CONFIG['level'],
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ProductionBot')

class ProductionArbitrageBot:
    """Главный класс производственного арбитражного бота"""
    
    def __init__(self):
        self.ws_manager = None
        self.trading_engine = TradingEngine()
        self.orderbooks = defaultdict(dict)  # {symbol: {exchange: OrderBook}}
        self.active_pairs = set()
        self.running = False
        self.last_pair_update = 0
        self.scan_counter = 0
        self.opportunity_queue = asyncio.Queue()
        self.statistics = {
            'start_time': time.time(),
            'scans': 0,
            'opportunities_found': 0,
            'trades_executed': 0,
            'ws_messages': 0,
            'errors': 0
        }
        
    async def start(self):
        """Запуск бота"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК PRODUCTION ARBITRAGE BOT v1.0.0")
        logger.info(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"💼 Режим: {TRADING_CONFIG['mode'].upper()}")
        logger.info(f"💰 Мин. прибыль: {TRADING_CONFIG['min_profit_threshold']}%")
        logger.info("=" * 60)
        
        self.running = True
        
        try:
            # Инициализация
            await self._initialize()
            
            # Запуск основных компонентов
            tasks = [
                self._run_websocket_manager(),
                self._run_scanner(),
                self._run_executor(),
                self._run_pair_updater(),
                self._run_statistics()
            ]
            
            # Запуск торгового движка
            await self.trading_engine.start()
            
            # Запуск всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("\n⚠️ Получен сигнал остановки")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка бота"""
        logger.info("\n🛑 Остановка бота...")
        self.running = False
        
        # Остановка компонентов
        if self.ws_manager:
            await self.ws_manager.stop()
        
        await self.trading_engine.stop()
        
        # Финальная статистика
        self._print_final_statistics()
        
        logger.info("✅ Бот остановлен")
    
    async def _initialize(self):
        """Инициализация бота"""
        logger.info("🔧 Инициализация...")
        
        # Загрузка торговых пар
        await self._discover_trading_pairs()
        
        # Инициализация WebSocket менеджера
        self.ws_manager = WebSocketManager(
            on_orderbook_update=self._on_orderbook_update
        )
        
        logger.info(f"✅ Инициализация завершена. Активных пар: {len(self.active_pairs)}")
    
    async def _discover_trading_pairs(self):
        """Динамическое обнаружение торговых пар"""
        logger.info("🔍 Поиск торговых пар...")
        
        all_pairs = defaultdict(set)  # {symbol: set(exchanges)}
        
        for exchange_id, config in EXCHANGES_CONFIG.items():
            if not config['enabled']:
                continue
                
            try:
                pairs = await self._fetch_exchange_pairs(exchange_id)
                for pair in pairs:
                    all_pairs[pair].add(exchange_id)
                    
                logger.info(f"✅ {config['name']}: {len(pairs)} пар")
                
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки пар {config['name']}: {e}")
        
        # Фильтрация пар
        self.active_pairs = set()
        for symbol, exchanges in all_pairs.items():
            # Пара должна быть минимум на N биржах
            if len(exchanges) >= DYNAMIC_PAIRS_CONFIG['min_exchanges']:
                self.active_pairs.add(symbol)
        
        # Ограничение количества пар
        if len(self.active_pairs) > DYNAMIC_PAIRS_CONFIG['max_pairs']:
            # Оставляем только топовые пары
            priority_pairs = [
                'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 
                'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT',
                'DOT/USDT', 'TRX/USDT', 'AVAX/USDT', 'SHIB/USDT',
                'LINK/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT',
                'ETC/USDT', 'XLM/USDT', 'APT/USDT', 'ARB/USDT'
            ]
            
            final_pairs = set()
            for pair in priority_pairs:
                if pair in self.active_pairs:
                    final_pairs.add(pair)
            
            # Добавляем остальные до лимита
            for pair in self.active_pairs:
                if len(final_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                    break
                final_pairs.add(pair)
            
            self.active_pairs = final_pairs
        
        logger.info(f"📊 Найдено {len(self.active_pairs)} активных пар для арбитража")
        
        # Обновление времени
        self.last_pair_update = time.time()
    
    async def _fetch_exchange_pairs(self, exchange_id: str) -> List[str]:
        """Получить список пар с биржи"""
        if exchange_id not in EXCHANGES_CONFIG:
            logger.error(f"Exchange {exchange_id} not found in EXCHANGES_CONFIG")
            logger.error(f"Available exchanges: {list(EXCHANGES_CONFIG.keys())}")
            return []
        
        config = EXCHANGES_CONFIG[exchange_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                if exchange_id == 'mexc':
                    url = f"{config['rest_url']}/api/v3/exchangeInfo"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data.get('symbols', []):
                            # MEXC использует строковый статус: "1" = активен
                            if symbol.get('status') == '1' and symbol.get('quoteAsset') == 'USDT':
                                base = symbol['baseAsset']
                                pairs.append(f"{base}/USDT")
                        return pairs[:100]
                        
                elif exchange_id == 'bybit':
                    url = f"{config['rest_url']}/v5/market/instruments-info?category=spot"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data['result']['list']:
                            if symbol['status'] == 'Trading' and 'USDT' in symbol['symbol']:
                                base = symbol['symbol'].replace('USDT', '')
                                pairs.append(f"{base}/USDT")
                        return pairs[:100]
                        
                elif exchange_id == 'huobi':
                    url = f"{config['rest_url']}/v1/common/symbols"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data.get('data', []):
                            if symbol['state'] == 'online' and symbol['quote-currency'] == 'usdt':
                                pairs.append(f"{symbol['base-currency'].upper()}/USDT")
                        return pairs[:100]
                        
                # Для остальных бирж возвращаем базовый список
                else:
                    return [
                        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
                        'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT'
                    ]
                    
        except Exception as e:
            logger.error(f"Ошибка получения пар {exchange_id}: {e}")
            return []
    
    async def _on_orderbook_update(self, orderbook: OrderBook):
        """Обработчик обновления стакана"""
        try:
            # Сохраняем стакан
            if orderbook.symbol in self.active_pairs:
                if orderbook.symbol not in self.orderbooks:
                    self.orderbooks[orderbook.symbol] = {}
                    
                self.orderbooks[orderbook.symbol][orderbook.exchange] = orderbook
                self.statistics['ws_messages'] += 1
                
        except Exception as e:
            logger.error(f"Ошибка обработки orderbook: {e}")
            self.statistics['errors'] += 1
    
    async def _run_websocket_manager(self):
        """Запуск WebSocket менеджера"""
        try:
            await self.ws_manager.start(list(self.active_pairs))
        except Exception as e:
            logger.error(f"Ошибка WebSocket менеджера: {e}")
    
    async def _run_scanner(self):
        """Сканер арбитражных возможностей"""
        logger.info("🔍 Запуск сканера арбитража...")
        
        while self.running:
            try:
                self.scan_counter += 1
                opportunities_found = 0
                
                # Сканирование межбиржевого арбитража
                for symbol, exchanges_data in self.orderbooks.items():
                    if len(exchanges_data) < 2:
                        continue
                    
                    opportunity = self._check_inter_exchange_arbitrage(
                        symbol, exchanges_data
                    )
                    
                    if opportunity:
                        await self.opportunity_queue.put(opportunity)
                        opportunities_found += 1
                        
                        logger.info(
                            f"💎 Найдена возможность: {symbol} "
                            f"{opportunity.exchanges[0]}→{opportunity.exchanges[1]} "
                            f"Прибыль: {opportunity.expected_profit_pct:.3f}%"
                        )
                
                # Обновление статистики
                self.statistics['scans'] += 1
                if opportunities_found > 0:
                    self.statistics['opportunities_found'] += opportunities_found
                
                # Задержка между сканами
                await asyncio.sleep(TRADING_CONFIG['scan_interval'])
                
            except Exception as e:
                logger.error(f"Ошибка сканера: {e}")
                self.statistics['errors'] += 1
                await asyncio.sleep(5)
    
    def _check_inter_exchange_arbitrage(
        self, 
        symbol: str, 
        exchanges_data: Dict[str, OrderBook]
    ) -> Optional[ArbitrageOpportunity]:
        """Проверка межбиржевого арбитража"""
        try:
            # Находим лучшие цены
            best_bid = None
            best_bid_exchange = None
            best_bid_volume = 0
            best_ask = None
            best_ask_exchange = None
            best_ask_volume = 0
            
            # Собираем все цены для логирования
            prices_info = []
            
            for exchange, orderbook in exchanges_data.items():
                # Проверка свежести данных
                if orderbook.age > TRADING_CONFIG['max_opportunity_age']:
                    logger.debug(f"  {exchange}: Данные устарели (возраст: {orderbook.age:.1f}s)")
                    continue
                
                if orderbook.best_bid and orderbook.best_ask:
                    prices_info.append(f"{exchange}: bid={orderbook.best_bid:.4f}, ask={orderbook.best_ask:.4f}")
                
                if orderbook.best_bid and (not best_bid or orderbook.best_bid > best_bid):
                    best_bid = orderbook.best_bid
                    best_bid_exchange = exchange
                    best_bid_volume = orderbook.get_depth_volume(1)['bid']
                
                if orderbook.best_ask and (not best_ask or orderbook.best_ask < best_ask):
                    best_ask = orderbook.best_ask
                    best_ask_exchange = exchange
                    best_ask_volume = orderbook.get_depth_volume(1)['ask']
            
            # Логируем собранные цены каждые 100 проверок
            if hasattr(self, '_check_counter'):
                self._check_counter += 1
            else:
                self._check_counter = 1
                
            if self._check_counter % 100 == 0 and prices_info:
                logger.info(f"📊 {symbol} цены: {' | '.join(prices_info[:3])}")
            
            if not (best_bid and best_ask):
                if self._check_counter % 500 == 0:
                    logger.debug(f"  {symbol}: Недостаточно данных (bid={best_bid}, ask={best_ask})")
                return None
                
            if best_bid_exchange == best_ask_exchange:
                return None
            
            # Расчет прибыли
            spread_pct = (best_bid - best_ask) / best_ask * 100
            
            # Учет комиссий - используем maker где возможно для снижения затрат
            # MEXC: 0% maker, Bybit: 0.01% maker, остальные используем taker
            
            # Безопасное получение комиссий с дефолтными значениями
            if best_ask_exchange in EXCHANGES_CONFIG:
                if best_ask_exchange == 'mexc':
                    buy_fee = EXCHANGES_CONFIG[best_ask_exchange]['fees']['maker'] * 100
                elif best_ask_exchange == 'bybit':
                    buy_fee = EXCHANGES_CONFIG[best_ask_exchange]['fees']['maker'] * 100
                else:
                    buy_fee = EXCHANGES_CONFIG[best_ask_exchange]['fees']['taker'] * 100
            else:
                # Дефолтная комиссия если биржа не в конфиге
                buy_fee = 0.1  # 0.1% taker fee по умолчанию
                
            if best_bid_exchange in EXCHANGES_CONFIG:
                if best_bid_exchange == 'mexc':
                    sell_fee = EXCHANGES_CONFIG[best_bid_exchange]['fees']['maker'] * 100
                elif best_bid_exchange == 'bybit':
                    sell_fee = EXCHANGES_CONFIG[best_bid_exchange]['fees']['maker'] * 100
                else:
                    sell_fee = EXCHANGES_CONFIG[best_bid_exchange]['fees']['taker'] * 100
            else:
                # Дефолтная комиссия если биржа не в конфиге  
                sell_fee = 0.1  # 0.1% taker fee по умолчанию
                
            total_fees = buy_fee + sell_fee
            
            # Учет слиппеджа
            slippage = TRADING_CONFIG['slippage_tolerance'] * 100
            
            # Чистая прибыль
            net_profit_pct = spread_pct - total_fees - slippage
            
            # Детальное логирование для близких к порогу возможностей
            if spread_pct > 0:
                if self._check_counter % 50 == 0 or net_profit_pct > -0.1:
                    logger.info(f"🔍 {symbol}: {best_ask_exchange}→{best_bid_exchange}")
                    logger.info(f"   Спред: {spread_pct:.4f}% (bid={best_bid:.4f}, ask={best_ask:.4f})")
                    logger.info(f"   Комиссии: {total_fees:.4f}% (покупка={buy_fee:.3f}%, продажа={sell_fee:.3f}%)")
                    logger.info(f"   Слиппедж: {slippage:.3f}%")
                    logger.info(f"   Чистая прибыль: {net_profit_pct:.4f}% (порог: {TRADING_CONFIG['min_profit_threshold']}%)")
                    logger.info(f"   Объемы: bid={best_bid_volume:.2f}, ask={best_ask_volume:.2f}")
            
            if net_profit_pct < TRADING_CONFIG['min_profit_threshold']:
                return None
            
            # НАЙДЕНА ВОЗМОЖНОСТЬ!
            logger.warning(f"🎯 АРБИТРАЖ НАЙДЕН! {symbol}: {best_ask_exchange}→{best_bid_exchange}, прибыль: {net_profit_pct:.4f}%")
            
            # Минимальный объем
            min_volume = min(best_bid_volume, best_ask_volume) * best_ask
            
            # Расчет прибыли в USD
            position_size = min(
                min_volume * 0.1,  # 10% от доступного объема
                1000  # Максимум $1000
            )
            expected_profit_usd = position_size * net_profit_pct / 100
            
            return ArbitrageOpportunity(
                type='inter_exchange',
                path=[best_ask_exchange, best_bid_exchange],
                exchanges=[best_ask_exchange, best_bid_exchange],
                symbols=[symbol],
                prices={
                    f'{best_ask_exchange}_ask': best_ask,
                    f'{best_bid_exchange}_bid': best_bid
                },
                volumes={
                    best_ask_exchange: best_ask_volume,
                    best_bid_exchange: best_bid_volume
                },
                expected_profit_pct=net_profit_pct,
                expected_profit_usd=expected_profit_usd,
                min_volume=min_volume
            )
            
        except Exception as e:
            logger.error(f"Ошибка проверки арбитража: {e}")
            return None
    
    async def _run_executor(self):
        """Исполнитель арбитражных сделок"""
        logger.info("💼 Запуск исполнителя сделок...")
        
        while self.running:
            try:
                # Ожидание возможности
                opportunity = await asyncio.wait_for(
                    self.opportunity_queue.get(),
                    timeout=10
                )
                
                # Проверка свежести
                if not opportunity.is_fresh:
                    logger.warning("⚠️ Возможность устарела")
                    continue
                
                # Исполнение
                success = await self.trading_engine.execute_arbitrage(opportunity)
                
                if success:
                    self.statistics['trades_executed'] += 1
                    logger.info(f"✅ Сделка исполнена успешно")
                else:
                    logger.warning(f"❌ Сделка не исполнена")
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Ошибка исполнителя: {e}")
                self.statistics['errors'] += 1
                await asyncio.sleep(1)
    
    async def _run_pair_updater(self):
        """Периодическое обновление торговых пар"""
        while self.running:
            try:
                # Проверка времени последнего обновления
                if time.time() - self.last_pair_update > DYNAMIC_PAIRS_CONFIG['update_interval']:
                    logger.info("🔍 Обнаружение торговых пар...")
                    try:
                        await self.discover_pairs()
                    except Exception as e:
                        logger.error(f"Ошибка при обнаружении пар: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        raise
                    
                    if not self.active_pairs:
                        raise Exception("Нет активных торговых пар")
                    
                    # Перезапуск WebSocket с новыми парами
                    await self.ws_manager.stop()
                    await asyncio.sleep(2)
                    asyncio.create_task(
                        self.ws_manager.start(list(self.active_pairs))
                    )
                
                await asyncio.sleep(60)  # Проверка каждую минуту
                
            except Exception as e:
                logger.error(f"Ошибка обновления пар: {e}")
                await asyncio.sleep(300)
    
    async def _run_statistics(self):
        """Периодический вывод статистики"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Каждую минуту
                
                runtime = (time.time() - self.statistics['start_time']) / 60
                ws_stats = self.ws_manager.get_statistics() if self.ws_manager else {}
                trading_stats = self.trading_engine.get_stats()
                
                logger.info("=" * 50)
                logger.info("📊 СТАТИСТИКА РАБОТЫ")
                logger.info(f"⏱️ Время работы: {runtime:.1f} мин")
                logger.info(f"🔍 Сканирований: {self.statistics['scans']}")
                logger.info(f"💎 Найдено возможностей: {self.statistics['opportunities_found']}")
                logger.info(f"💼 Исполнено сделок: {self.statistics['trades_executed']}")
                logger.info(f"📨 WebSocket сообщений: {self.statistics['ws_messages']}")
                logger.info(f"❌ Ошибок: {self.statistics['errors']}")
                
                if ws_stats:
                    logger.info(f"🔌 Подключено бирж: {len(ws_stats.get('connected', []))}")
                    
                logger.info(f"💰 Прибыль: ${trading_stats.get('total_profit_usd', 0):.2f} "
                          f"({trading_stats.get('total_profit_pct', 0):.3f}%)")
                logger.info(f"📦 Объем торгов: ${trading_stats.get('total_volume', 0):.2f}")
                logger.info("=" * 50)
                
            except Exception as e:
                logger.error(f"Ошибка статистики: {e}")
    
    def _print_final_statistics(self):
        """Вывод финальной статистики"""
        runtime = (time.time() - self.statistics['start_time']) / 3600
        trading_stats = self.trading_engine.get_stats()
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        logger.info("=" * 60)
        logger.info(f"⏱️ Время работы: {runtime:.2f} часов")
        logger.info(f"🔍 Всего сканирований: {self.statistics['scans']}")
        logger.info(f"💎 Найдено возможностей: {self.statistics['opportunities_found']}")
        logger.info(f"💼 Исполнено сделок: {self.statistics['trades_executed']}")
        logger.info(f"✅ Успешных сделок: {trading_stats.get('successful', 0)}")
        logger.info(f"❌ Неудачных сделок: {trading_stats.get('failed', 0)}")
        logger.info(f"📨 WebSocket сообщений: {self.statistics['ws_messages']}")
        logger.info(f"⚠️ Ошибок: {self.statistics['errors']}")
        logger.info(f"💰 Общая прибыль: ${trading_stats.get('total_profit_usd', 0):.2f}")
        logger.info(f"📊 Прибыль %: {trading_stats.get('total_profit_pct', 0):.3f}%")
        logger.info(f"📦 Общий объем: ${trading_stats.get('total_volume', 0):.2f}")
        logger.info("=" * 60)

async def main():
    """Главная функция"""
    bot = ProductionArbitrageBot()
    
    # Обработка сигналов остановки
    def signal_handler(sig, frame):
        logger.info("\n⚠️ Получен сигнал остановки...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Запуск бота
    await bot.start()

if __name__ == "__main__":
    # Запуск
    asyncio.run(main())
