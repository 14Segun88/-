"""
Symbol normalization helpers.
Ensures consistent symbol format across components: BASE/QUOTE (e.g., BTC/USDT), uppercase.
"""
from typing import Optional

# Recognized quote currencies, ordered by typical priority/length
KNOWN_QUOTES = (
    "USDT", "USDC", "BUSD", "USD", "BTC", "ETH"
)

def normalize_symbol(symbol: Optional[str]) -> Optional[str]:
    """Normalize various symbol representations to 'BASE/QUOTE' uppercase.
    Examples:
    - 'btcusdt' -> 'BTC/USDT'
    - 'BTC_USDT' -> 'BTC/USDT'
    - 'BTC-USDT' -> 'BTC/USDT'
    - 'BTC/USDT' -> 'BTC/USDT'
    - 'ETHUSDC' -> 'ETH/USDC'
    Returns None if input is falsy.
    """
    if not symbol:
        return None

    s = symbol.strip().upper()
    if not s:
        return None

    # Fast path: already BASE/QUOTE
    if '/' in s:
        base, *rest = s.split('/')
        if not rest:
            return s  # malformed but keep
        quote = rest[0]
        return f"{base}/{quote}"

    # Replace common separators with '/'
    s_sep = s.replace('-', '/').replace('_', '/')
    if '/' in s_sep and s_sep.count('/') == 1:
        base, quote = s_sep.split('/')
        return f"{base}/{quote}"

    # No separators: try to split by known quotes suffix
    for q in KNOWN_QUOTES:
        if s.endswith(q):
            base = s[:-len(q)]
            if base:
                return f"{base}/{q}"
            break

    # Fallback: return as-is (uppercase)
    return s


def is_normalized(symbol: Optional[str]) -> bool:
    if not symbol:
        return False
    norm = normalize_symbol(symbol)
    return norm == symbol
