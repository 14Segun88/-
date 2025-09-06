"""
Конфиг‑утилиты для Tiger Trade проекта.
Загружает ключи/настройки из .env/окружения и задаёт пути данных/артефактов.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]  # .../splitwise (корень репозитория)
TT_ROOT = ROOT / "tiger_trade"

# Явно пытаемся загрузить .env из корня репозитория и из каталога tiger_trade/.
# Это удобно: можно положить ключи в любой из этих файлов; значения из окружения
# всегда имеют приоритет над .env.
load_dotenv(ROOT / ".env")
load_dotenv(TT_ROOT / ".env")

DATA_ROOT = TT_ROOT / "data" / "external" / "TigerTrade"
OUT_ROOT = TT_ROOT / "out"


@dataclass(frozen=True)
class Config:
    tiger_api_key: Optional[str]
    tiger_base_url: Optional[str]
    ndq_api_key: Optional[str]

    cme_symbol_6e: str
    tt_symbol_eurusd: str
    tz: str

    data_root: Path = DATA_ROOT
    out_root: Path = OUT_ROOT

    @staticmethod
    def from_env() -> "Config":
        return Config(
            tiger_api_key=os.getenv("TIGER_API_KEY"),
            tiger_base_url=os.getenv("TIGER_BASE_URL"),
            ndq_api_key=os.getenv("NDAQ_API_KEY") or os.getenv("QUANDL_API_KEY"),
            cme_symbol_6e=os.getenv("CME_SYMBOL_6E", "6E"),
            tt_symbol_eurusd=os.getenv("TT_SYMBOL_EURUSD", "EURUSD"),
            tz=os.getenv("TZ", "UTC"),
        )


def ensure_dirs(cfg: Config) -> None:
    """Создаёт базовые каталоги данных/выходов, если их нет."""
    (cfg.data_root / "EURUSD").mkdir(parents=True, exist_ok=True)
    (cfg.data_root / "6E").mkdir(parents=True, exist_ok=True)
    (cfg.data_root / "6E_daily").mkdir(parents=True, exist_ok=True)
    cfg.out_root.mkdir(parents=True, exist_ok=True)
