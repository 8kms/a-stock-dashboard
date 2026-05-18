"""
Factor Computation Engine — 15-Dimension Price-Volume Factor Vector
All factors computed from 30-day OHLCV, z-score normalized cross-sectionally.
"""
import numpy as np
from typing import List, Dict, Optional


FACTOR_DEFS = {
    'ret_5d':         '5日收益率',
    'ret_20d':        '20日收益率',
    'avg_amplitude':  '平均日内振幅',
    'avg_turnover':   '平均换手率',
    'avg_vol_ratio':  '平均量比',
    'upper_shadow':   '平均上影线占比',
    'lower_shadow':   '平均下影线占比',
    'close_position': '收盘位置分位',
    'body_ratio':     '实体/振幅比',
    'vol_trend':      '量能趋势斜率',
    'vwap_deviation': 'VWAP偏离度',
    'consecutive':    '连阳/连阴强度',
    'high_proximity': '距离20日高点',
    'low_proximity':  '距离20日低点',
    'volatility':     '波动率',
}


def compute_factors(klines: List[Dict], window: int = 30) -> Dict[str, float]:
    """
    Compute 15 price-volume factors from OHLCV kline data.

    Args:
        klines: List of dicts with keys: open, close, high, low, volume
        window: Rolling window size (default 30 trading days)

    Returns:
        Dict of factor_name -> value (raw, not normalized)
    """
    if len(klines) < 5:
        return {}

    # Tail the window
    data = klines[-window:] if len(klines) >= window else klines
    n = len(data)

    closes = np.array([k['close'] for k in data], dtype=np.float64)
    opens  = np.array([k['open']  for k in data], dtype=np.float64)
    highs  = np.array([k['high']  for k in data], dtype=np.float64)
    lows   = np.array([k['low']   for k in data], dtype=np.float64)
    volumes = np.array([k['volume'] for k in data], dtype=np.float64)

    # ── 1. Return factors ──
    ret_5d  = (closes[-1] / closes[-6] - 1) * 100 if n >= 6 else 0
    ret_20d = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else (closes[-1] / closes[0] - 1) * 100

    # ── 2. Amplitude ──
    daily_amp = (highs - lows) / closes * 100
    avg_amplitude = np.mean(daily_amp)

    # ── 3. Volume-based factors (using volume changes as proxy for turnover ratio) ──
    vol_ma5  = np.mean(volumes[-5:]) if n >= 5 else np.mean(volumes)
    vol_ma20 = np.mean(volumes[-20:]) if n >= 20 else np.mean(volumes)
    vol_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0
    avg_vol_ratio = float(vol_ratio)

    # ── 4. Shadow ratios (all in % of amplitude) ──
    amp_abs = highs - lows  # absolute amplitude in yuan
    body_high = np.maximum(opens, closes)
    body_low  = np.minimum(opens, closes)
    upper_shadows = np.where(amp_abs > 0, (highs - body_high) / amp_abs * 100, 0)
    lower_shadows = np.where(amp_abs > 0, (body_low - lows) / amp_abs * 100, 0)
    avg_upper_shadow = np.mean(upper_shadows)
    avg_lower_shadow = np.mean(lower_shadows)

    # ── 5. Close position (0-100 scale, using absolute amplitude) ──
    close_pos = np.where(amp_abs > 0, (closes - lows) / amp_abs * 100, 50)
    avg_close_position = np.mean(close_pos)

    # ── 6. Body/amplitude ratio (0-100 scale, using absolute amplitude) ──
    body_size = np.abs(closes - opens)
    body_ratios = np.where(amp_abs > 0, body_size / amp_abs * 100, 0)
    avg_body_ratio = np.mean(body_ratios)

    # ── 7. Volume trend slope (linear regression on log volume) ──
    log_vol = np.log(volumes + 1)
    x = np.arange(n)
    if n > 1:
        slope = np.polyfit(x, log_vol, 1)[0]
        vol_trend = float(slope * 100)  # percentage trend
    else:
        vol_trend = 0.0

    # ── 8. VWAP deviation ──
    typical_price = (highs + lows + closes) / 3
    vwap = np.sum(typical_price * volumes) / np.sum(volumes) if np.sum(volumes) > 0 else closes[-1]
    vwap_deviation = (closes[-1] / vwap - 1) * 100 if vwap > 0 else 0

    # ── 9. Consecutive up/down ──
    direction = np.sign(np.diff(closes[-10:])) if n >= 11 else np.sign(np.diff(closes))
    consecutive = 0
    if len(direction) > 0:
        last_dir = direction[-1]
        for d in reversed(direction):
            if d == last_dir:
                consecutive += 1 if last_dir > 0 else -1
            else:
                break
    consecutive = float(consecutive)

    # ── 10. High proximity (distance from 20-day high) ──
    high_20d = np.max(highs[-20:]) if n >= 20 else np.max(highs)
    high_proximity = (closes[-1] / high_20d - 1) * 100 if high_20d > 0 else 0

    # ── 11. Low proximity (distance from 20-day low) ──
    low_20d = np.min(lows[-20:]) if n >= 20 else np.min(lows)
    low_proximity = (closes[-1] / low_20d - 1) * 100 if low_20d > 0 else 0

    # ── 12. Volatility ──
    daily_returns = np.diff(closes) / closes[:-1] * 100
    volatility = np.std(daily_returns) if len(daily_returns) > 1 else 0.0

    # ── 13. Average turnover (proxy from volume/market_cap if available) ──
    # Without market cap, use normalized volume
    avg_volume = np.mean(volumes)
    vol_cv = np.std(volumes) / avg_volume if avg_volume > 0 else 0
    avg_turnover = float(vol_cv * 100)  # coefficient of variation as turnover proxy

    return {
        'ret_5d':          round(ret_5d, 4),
        'ret_20d':         round(ret_20d, 4),
        'avg_amplitude':   round(avg_amplitude, 4),
        'avg_turnover':    round(avg_turnover, 4),
        'avg_vol_ratio':   round(avg_vol_ratio, 4),
        'upper_shadow':    round(avg_upper_shadow, 4),
        'lower_shadow':    round(avg_lower_shadow, 4),
        'close_position':  round(avg_close_position, 4),
        'body_ratio':      round(avg_body_ratio, 4),
        'vol_trend':       round(vol_trend, 4),
        'vwap_deviation':  round(vwap_deviation, 4),
        'consecutive':     round(consecutive, 4),
        'high_proximity':  round(high_proximity, 4),
        'low_proximity':   round(low_proximity, 4),
        'volatility':      round(volatility, 4),
    }


def factor_vector(factors: Dict[str, float], factor_names: Optional[List[str]] = None) -> np.ndarray:
    """Convert factor dict to ordered numpy vector."""
    if factor_names is None:
        factor_names = list(FACTOR_DEFS.keys())
    return np.array([factors.get(f, 0.0) for f in factor_names], dtype=np.float64)


def zscore_normalize(factor_matrix: np.ndarray) -> np.ndarray:
    """
    Z-score normalize factor matrix cross-sectionally.
    factor_matrix: (n_stocks, n_factors)
    Returns normalized matrix, replacing NaN/Inf with 0.
    """
    mean = np.nanmean(factor_matrix, axis=0)
    std = np.nanstd(factor_matrix, axis=0)
    std = np.where(std == 0, 1.0, std)
    normalized = (factor_matrix - mean) / std
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)
    return normalized


def euclidean_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute similarity score from z-score normalized vectors.
    Uses Euclidean distance converted to similarity: 1 / (1 + distance)
    Range: (0, 1], 1 = perfect match.
    """
    dist = np.sqrt(np.sum((vec_a - vec_b) ** 2))
    return float(1.0 / (1.0 + dist))


def structure_classify(factors: Dict[str, float]) -> str:
    """
    Rule-based structure classification (human-readable label).
    Classifies into one of 9 structure types.
    """
    ret_5d = factors.get('ret_5d', 0)
    ret_20d = factors.get('ret_20d', 0)
    body_r = factors.get('body_ratio', 50)
    close_p = factors.get('close_position', 50)
    upper_s = factors.get('upper_shadow', 0)
    lower_s = factors.get('lower_shadow', 0)
    vol_r = factors.get('avg_vol_ratio', 1)
    vol_t = factors.get('vol_trend', 0)
    high_p = factors.get('high_proximity', 0)

    # Breakout detection
    if ret_5d > 5 and vol_r > 1.5 and close_p > 70:
        return '放量突破'
    if ret_5d > 5 and vol_r < 1.0 and close_p > 60:
        return '缩量上涨'

    # Pullback detection
    if -3 < ret_5d < 1 and ret_20d > 10 and vol_r < 0.8:
        return '缩量回踩'
    if ret_5d < -3 and vol_r > 1.5 and close_p < 30:
        return '放量下跌'

    # High-level patterns
    if ret_20d > 20 and upper_s > 30 and vol_r > 2:
        return '高位长上影分歧'
    if ret_20d > 20 and ret_5d < 3 and ret_5d > -1 and vol_r > 2:
        return '高位放量滞涨'
    if ret_20d > 30 and upper_s > 25 and close_p < 50:
        return '高位冲高回落'

    # Low-level patterns
    if ret_20d < -15 and vol_t > 0 and vol_r > 1.2 and close_p > 60:
        return '低位放量企稳'
    if ret_20d < -10 and vol_r < 0.7 and close_p > 50:
        return '低位缩量筑底'

    # Default
    if vol_r > 1.5 and body_r > 60:
        return '放量博弈'
    if vol_r < 0.6:
        return '缩量横盘'

    return '震荡整理'


if __name__ == '__main__':
    # Quick test with mock data
    import random
    random.seed(42)
    mock_klines = []
    price = 50.0
    for i in range(35):
        change = random.gauss(0, 0.02)
        price *= (1 + change)
        high = price * random.uniform(1.0, 1.04)
        low = price * random.uniform(0.96, 1.0)
        open_p = low + random.random() * (high - low)
        vol = random.randint(500000, 5000000)
        mock_klines.append({
            'date': f'2026-05-{i+1:02d}',
            'open': round(open_p, 2),
            'close': round(price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'volume': vol,
        })

    factors = compute_factors(mock_klines)
    print("Factors:")
    for k, v in factors.items():
        print(f"  {k:20s} = {v:10.4f}  ({FACTOR_DEFS[k]})")
    print(f"\nStructure: {structure_classify(factors)}")
    print(f"Vector shape: {factor_vector(factors).shape}")
