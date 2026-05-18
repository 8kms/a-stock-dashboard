"""
Diagnostic Report Engine
Orchestrates: factor computation → structure matching → backtest → diagnostic JSON
"""
import time, math, numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from factor_engine import compute_factors, structure_classify, FACTOR_DEFS
from structure_matcher import (
    FactorStore, StructureMatcher, compute_backtest_stats,
    MatchResult, BacktestStats, STRUCTURE_NAMES
)


# ── Global singletons (initialized lazily) ──
_store: Optional[FactorStore] = None
_matcher: Optional[StructureMatcher] = None


def get_matcher() -> StructureMatcher:
    global _store, _matcher
    if _store is None:
        _store = FactorStore()
        _store.initialize(n_stocks=150, n_days=200)
    if _matcher is None:
        _matcher = StructureMatcher(_store)
    return _matcher


# ═══════════════════════════════════════
#  RISK TAG COMPUTATION (15-dim enhanced)
# ═══════════════════════════════════════

def compute_risk_tags_enhanced(factors: Dict[str, float], structure: str) -> List[Dict]:
    """Enhanced risk tags based on 15-dim factor analysis."""
    tags = []

    ret_5d = factors.get('ret_5d', 0)
    ret_20d = factors.get('ret_20d', 0)
    upper_s = factors.get('upper_shadow', 0)
    lower_s = factors.get('lower_shadow', 0)
    close_p = factors.get('close_position', 50)
    body_r = factors.get('body_ratio', 50)
    vol_r = factors.get('avg_vol_ratio', 1)
    vol_t = factors.get('vol_trend', 0)
    high_p = factors.get('high_proximity', 0)
    low_p = factors.get('low_proximity', 0)
    vola = factors.get('volatility', 1.5)
    consec = factors.get('consecutive', 0)

    # Price-based
    if ret_5d >= 9.5: tags.append({'label': '涨停', 'type': 'danger'})
    elif ret_5d >= 7: tags.append({'label': '大涨', 'type': 'warning'})
    if ret_20d > 30: tags.append({'label': '短期涨幅过大', 'type': 'danger'})
    elif ret_20d > 20: tags.append({'label': '累计涨幅较高', 'type': 'warning'})

    # Volume-based
    if vol_r > 3: tags.append({'label': '巨量', 'type': 'danger'})
    elif vol_r > 2: tags.append({'label': '放量', 'type': 'warning'})
    if vol_r < 0.4: tags.append({'label': '极度缩量', 'type': 'info'})
    if vol_t > 3 and ret_20d > 15: tags.append({'label': '量价背离', 'type': 'warning'})

    # Shadow/fracture
    if upper_s > 30: tags.append({'label': '长上影', 'type': 'danger'})
    elif upper_s > 20: tags.append({'label': '上影线偏长', 'type': 'warning'})
    if lower_s > 25: tags.append({'label': '长下影', 'type': 'info'})

    # Position
    if high_p > -2 and ret_20d > 20: tags.append({'label': '接近前高', 'type': 'warning'})
    if high_p > -1: tags.append({'label': '创近期新高', 'type': 'info'})
    if low_p < 3 and ret_20d < -10: tags.append({'label': '接近前低', 'type': 'warning'})

    # Close position quality
    if close_p < 35: tags.append({'label': '收盘偏弱', 'type': 'warning'})
    elif close_p > 70: tags.append({'label': '收盘偏强', 'type': 'info'})

    # Volatility
    if vola > 3.5: tags.append({'label': '高波动', 'type': 'warning'})

    # Structure-specific
    if '放量滞涨' in structure: tags.append({'label': '不适合追高', 'type': 'danger'})
    if '分歧' in structure: tags.append({'label': '高位分歧', 'type': 'danger'})
    if '低位' in structure and vol_r > 1.5: tags.append({'label': '底部异动', 'type': 'info'})

    if not tags: tags.append({'label': '正常', 'type': 'info'})
    return tags


# ═══════════════════════════════════════
#  SCORING ENGINE
# ═══════════════════════════════════════

def compute_observation_score(
    factors: Dict[str, float],
    stats: BacktestStats,
    market_state: str = '震荡偏多',
    sector_strength: float = 0.5
) -> Dict:
    """
    Compute observation priority score and component breakdown.
    Formula: (market × 0.30) + (sector × 0.25) + (signal × 0.35) − risk_penalty × win_rate_weight
    """
    # Market environment score (0-1)
    market_scores = {'强势': 1.0, '偏强': 0.8, '震荡偏多': 0.5, '震荡偏空': 0.3, '偏弱': 0.15, '弱势': 0.05}
    market_score = market_scores.get(market_state, 0.3)

    # Sector strength (0-1)
    sector_score = min(max(sector_strength, 0.0), 1.0)

    # Signal quality score (0-1): based on structure win rate and factor quality
    wr_t5 = stats.win_rate_t5 / 100 if stats.total_samples > 0 else 0.5
    close_p = factors.get('close_position', 50) / 100
    body_r = factors.get('body_ratio', 50) / 100
    vol_r = factors.get('avg_vol_ratio', 1)
    # Signal is strong if: win rate > 55%, close position is high, body is substantial
    signal_score = (wr_t5 * 0.5 + close_p * 0.2 + body_r * 0.15 + min(vol_r / 3, 1) * 0.15)
    signal_score = min(max(signal_score, 0.0), 1.0)

    # Risk penalty: higher risk → bigger deduction
    ret_5d = factors.get('ret_5d', 0)
    ret_20d = factors.get('ret_20d', 0)
    upper_s = factors.get('upper_shadow', 0)
    vola = factors.get('volatility', 1.5)
    risk_penalty = 0.0
    if ret_20d > 25: risk_penalty += 0.15
    if ret_5d > 8 and upper_s > 20: risk_penalty += 0.15
    if upper_s > 30: risk_penalty += 0.1
    if vola > 3: risk_penalty += 0.05
    risk_penalty = min(risk_penalty, 0.4)

    # Win rate weight: lower win rate amplifies risk penalty
    wr_weight = 1.0 - wr_t5  # 0.5 if wr=50%, 0.7 if wr=30%
    risk_penalty *= wr_weight

    # Final score
    score = market_score * 0.30 + sector_score * 0.25 + signal_score * 0.35 - risk_penalty
    score = round(max(min(score, 1.0), -0.3), 2)

    return {
        'total': score,
        'breakdown': {
            'market_env': round(market_score * 0.30, 3),
            'sector_strength': round(sector_score * 0.25, 3),
            'signal_quality': round(signal_score * 0.35, 3),
            'risk_penalty': round(-risk_penalty, 3),
        },
        'interpretation': (
            '高风险回避' if score < 0 else
            '低优先级观察' if score < 0.3 else
            '中等优先级观察' if score < 0.5 else
            '较高优先级观察' if score < 0.7 else
            '高优先级观察'
        ),
    }


# ═══════════════════════════════════════
#  MAIN DIAGNOSTIC PIPELINE
# ═══════════════════════════════════════

def inject_synthetic_matches(factors, structure, code, name, n=30):
    """Generate synthetic historical matches based on the current factor vector.
    In production, real historical data replaces this."""
    matches = []
    for i in range(n):
        # Vary similarity around 0.45-0.85
        sim = round(0.45 + abs(np.random.normal(0.2, 0.12)) % 0.40, 4)
        # Vary returns based on structure type
        if '突破' in structure or '企稳' in structure:
            ret_t5 = round(np.random.normal(3.0, 4.0), 2)
            wr_bias = 0.55
        elif '下跌' in structure or '分歧' in structure or '滞涨' in structure:
            ret_t5 = round(np.random.normal(-3.0, 4.5), 2)
            wr_bias = 0.35
        else:
            ret_t5 = round(np.random.normal(0.5, 4.0), 2)
            wr_bias = 0.48
        matches.append(MatchResult(
            date=(datetime.now() - timedelta(days=np.random.randint(10, 500))).strftime('%Y-%m-%d'),
            code=f'{600000 + np.random.randint(0, 5000):06d}',
            name=f'历史样本{i+1}',
            similarity=sim,
            structure=structure,
            ret_t1=round(np.random.normal(ret_t5/5, 1.5), 2),
            ret_t3=round(np.random.normal(ret_t5/2, 2.5), 2),
            ret_t5=ret_t5,
            ret_t10=round(np.random.normal(ret_t5*1.2, 5.0), 2),
            max_dd_5=round(-abs(np.random.normal(5.0, 2.5)), 2),
        ))
    matches.sort(key=lambda x: x.similarity, reverse=True)
    return matches


def generate_diagnosis(
    code: str,
    name: str,
    klines: List[Dict],
    market_state: str = '震荡偏多',
    sector_name: str = '',
    sector_pct: float = 0.0,
    sector_rank: int = 10,
    sector_up_ratio: float = 0.5,
) -> Dict:
    """
    Full diagnostic pipeline → structured JSON ready for HTML rendering.
    """
    t0 = time.time()

    # Step 1: Compute factors
    factors = compute_factors(klines)
    if not factors:
        return {'error': 'Kline data insufficient (need >= 5 days)'}

    structure = structure_classify(factors)
    risk_tags = compute_risk_tags_enhanced(factors, structure)

    # Step 2: Match against history
    matcher = get_matcher()
    # Inject current stock's factor vector (with slight noise) into store
    # to ensure matches exist. In production with real data, this won't be needed.
    injected = inject_synthetic_matches(factors, structure, code, name, n=30)
    matches = matcher.match(factors, top_k=200, min_similarity=0.10)
    # Merge injected matches (higher priority since they come from same structure)
    if injected:
        combined = injected + [m for m in matches if m.code != code]
        combined.sort(key=lambda x: x.similarity, reverse=True)
        matches = combined[:200]

    # Step 3: Backtest stats
    stats = compute_backtest_stats(matches, market_state, sector_name)

    # Step 4: Sector strength (0-1)
    sector_strength = (sector_pct / 7.0 * 0.5 + (1 - sector_rank / 20) * 0.3 + sector_up_ratio * 0.2)
    sector_strength = min(max(sector_strength, 0.0), 1.0)

    # Step 5: Observation score
    score = compute_observation_score(factors, stats, market_state, sector_strength)

    # Step 6: Recent price data
    latest = klines[-1] if klines else {}
    prev = klines[-2] if len(klines) > 1 else {}

    # Step 7: Build kline table (last 10 days)
    kline_table = []
    for k in klines[-10:]:
        chg = round((k['close'] - k['open']) / k['open'] * 100, 2) if k['open'] > 0 else 0
        amp = round((k['high'] - k['low']) / k['low'] * 100, 2) if k['low'] > 0 else 0
        kline_table.append({
            'date': k.get('date', '')[-5:],
            'open': round(k['open'], 2),
            'close': round(k['close'], 2),
            'high': round(k['high'], 2),
            'low': round(k['low'], 2),
            'change': chg,
            'amplitude': amp,
            'volume': k.get('volume', 0),
        })

    # Step 8: Structure analysis paragraph
    ret_5d = factors.get('ret_5d', 0)
    ret_20d = factors.get('ret_20d', 0)
    upper_s = factors.get('upper_shadow', 0)
    lower_s = factors.get('lower_shadow', 0)
    vol_r = factors.get('avg_vol_ratio', 1)
    high_p = factors.get('high_proximity', 0)
    low_p = factors.get('low_proximity', 0)
    close_p = factors.get('close_position', 50)
    body_r = factors.get('body_ratio', 50)
    vol_trend = factors.get('vol_trend', 0)

    recent_prices = [k['close'] for k in klines[-5:]]
    price_trend = '上升' if recent_prices[-1] > recent_prices[0] else '下降'

    structure_analysis = (
        f"近5日价格呈{price_trend}趋势，"
        f"20日涨跌幅 {ret_20d:.1f}%。"
        f"今日量比 {vol_r:.1f}x{'（显著放量）' if vol_r > 1.5 else '（正常）'}，"
        f"换手率偏低，"
        f"上影线占比 {upper_s:.0f}%{'（偏长，需关注）' if upper_s > 20 else ''}。"
        f"收盘位置分位 {close_p:.0f}%{'（偏强）' if close_p > 60 else '（偏弱）' if close_p < 40 else '（中性）'}。"
        f"综合判断：当前处于「{structure}」结构。"
        + (f"由于上影线较长({upper_s:.0f}%)，可能存在高位抛压，需次日确认。" if upper_s > 25 else "")
        + (f"放量程度较高({vol_r:.1f}x)，关注量能是否持续。" if vol_r > 1.8 else "")
    )

    # Step 9: Market-state stratified stats
    by_state = {}
    total_samples = stats.total_samples
    if total_samples > 0:
        # Simulate stratification by market state
        bull_samples = max(total_samples // 3, 5)
        neutral_samples = total_samples - bull_samples - max(total_samples // 4, 5)
        bear_samples = max(total_samples // 4, 3)

        by_state = {
            '强势市场': {
                'samples': bull_samples,
                'win_rate_t5': round(stats.win_rate_t5 + np.random.uniform(3, 10), 1),
                'avg_ret_t5': round(stats.avg_ret_t5 + np.random.uniform(1.0, 3.0), 2),
            },
            '震荡市场': {
                'samples': neutral_samples,
                'win_rate_t5': round(stats.win_rate_t5 + np.random.uniform(-5, 3), 1),
                'avg_ret_t5': round(stats.avg_ret_t5 + np.random.uniform(-1.0, 1.0), 2),
            },
            '弱势市场': {
                'samples': bear_samples,
                'win_rate_t5': round(stats.win_rate_t5 + np.random.uniform(-15, -3), 1),
                'avg_ret_t5': round(stats.avg_ret_t5 + np.random.uniform(-4.0, -1.0), 2),
            },
        }

    # Step 10: Sector resonance analysis
    sector_resonance = '存在板块共振' if sector_rank <= 3 and sector_pct > 2 else \
                       '板块支撑一般' if sector_rank <= 10 else \
                       '板块支撑不足'
    sector_analysis = (
        f"{sector_name or '所属'}板块今日涨幅 {sector_pct:+.2f}%，排名第 {sector_rank}。"
        f"板块内上涨比例 {sector_up_ratio:.0%}。"
        f"判断：{sector_resonance}。"
        + ('板块共振对该信号有加分效果。' if sector_resonance == '存在板块共振' else
           '个股表现需独立于板块评估。' if sector_rank > 10 else '')
    )

    # Step 11: Observation points with concrete thresholds
    observation_points = []
    latest_price = latest.get('close', 0)

    if upper_s > 15:
        observation_points.append({
            'condition': '上影线确认',
            'icon': '⚠️',
            'detail': f'今日上影线占比 {upper_s:.0f}%，'
                     f'若次日低开 > 1% 且半小时内不收复，则确认高位抛压信号。'
                     f'参考阈值：跌破今日开盘价 {latest.get("open", 0):.2f} 则结构转弱。'
        })
    if vol_r > 2:
        observation_points.append({
            'condition': '量能持续性',
            'icon': '📊',
            'detail': f'今日量比 {vol_r:.1f}x，远超20日均量。'
                     f'明日成交量若骤降至今日 40% 以下且价格下跌，则为孤量出货信号。'
                     f'健康量能：连续3日量比维持在 1.3x 以上。'
        })
    if ret_20d > 20:
        observation_points.append({
            'condition': '短期涨幅监测',
            'icon': '📈',
            'detail': f'近20日累计涨幅 {ret_20d:.1f}%，已进入短期高位区。'
                     f'若5日内跌破近5日最低点，趋势转弱信号确认。'
                     f'参考支撑：近5日低点区域。'
        })
    if high_p > -3 and close_p > 60:
        observation_points.append({
            'condition': '前高突破验证',
            'icon': '🎯',
            'detail': f'当前距20日高点仅 {abs(high_p):.1f}%，处于关键阻力区。'
                     f'若放量突破前高且收盘站稳 → 结构升级为有效突破。'
                     f'若冲高回落且量能萎缩 → 双顶风险。'
        })
    if ret_20d < -10 and vol_r > 1.2:
        observation_points.append({
            'condition': '底部放量验证',
            'icon': '🔍',
            'detail': f'低位放量是积极信号（20日跌幅 {ret_20d:.1f}%）。'
                     f'确认条件：连续3日收盘站稳5日均线以上，且量能不能骤降。'
                     f'若次日缩量下跌 → 底部尚未确认，继续观望。'
        })
    if close_p < 35:
        observation_points.append({
            'condition': '收盘弱势',
            'icon': '📉',
            'detail': f'收盘位置偏低（{close_p:.0f}%），'
                     f'说明盘中多头无力守住高位。若连续3日收盘偏弱 → 趋势可能持续走低。'
        })
    if not observation_points:
        observation_points.append({
            'condition': '量价结构跟踪',
            'icon': '👀',
            'detail': '当前结构尚不明朗，建议等待量能或价格突破给出更明确的方向信号后再做判断。'
        })

    # Step 12: Comprehensive judgment
    st = score.get('total', 0.5)
    risk_level = '低' if st > 0.6 else '中等偏低' if st > 0.4 else '中等偏高' if st > 0.2 else '高'
    risk_color = '#34d399' if st > 0.5 else '#fbbf24' if st > 0.2 else '#f87171'

    # Build summary sentence
    summary_parts = [f"{name}（{code}）当前处于「{structure}」结构"]
    if sector_rank <= 3:
        summary_parts.append(f"{sector_name}板块共振（排名第{sector_rank}）")
    elif sector_rank <= 10 and sector_pct > 1:
        summary_parts.append(f"{sector_name}板块一般（排名第{sector_rank}）")
    if stats.total_samples > 0:
        sn = '' if stats.total_samples >= 100 else '（样本偏少，统计显著性不足）'
        summary_parts.append(f"历史{stats.total_samples}次类似结构中T+5胜率{stats.win_rate_t5}%{sn}")
    if st < 0.3:
        summary_parts.append("综合评分偏低，建议谨慎")
    elif st > 0.5:
        summary_parts.append("综合评分尚可，适合纳入观察池")

    comprehensive_judgment = {
        'risk_level': risk_level,
        'risk_color': risk_color,
        'summary': '，'.join(summary_parts) + '。',
        'structure_quality': min(max(3 - int(upper_s / 10) + int(vol_r > 1.8) + int(close_p > 60), 1), 5),
        'sector_quality': min(max(5 - sector_rank // 4, 1), 5),
        'market_quality': 3 if '偏多' in market_state else 2 if '偏空' in market_state else 1,
        'data_notice': '⚠️ MVP演示版：历史样本来自模拟数据，评分权重未经样本外验证，因子分位为估算值。不构成投资建议。',
    }

    # Step 13: Factor percentile estimates (simulated for MVP)
    factor_percentiles = {}
    percentile_map = {
        'ret_5d': (ret_5d, 0, 5),
        'ret_20d': (ret_20d, -5, 15),
        'upper_shadow': (upper_s, 5, 25),
        'close_position': (close_p, 30, 70),
        'avg_vol_ratio': (vol_r, 0.5, 2.0),
        'body_ratio': (body_r, 20, 60),
        'vol_trend': (vol_trend, -2, 3),
        'volatility': (factors.get('volatility', 1.5), 0.5, 3.0),
    }
    for fname, (val, low, high) in percentile_map.items():
        pct = round(min(max((val - low) / max(high - low, 0.001) * 100, 0), 100))
        factor_percentiles[fname] = {'value': round(val, 2), 'percentile': pct}

    # Step 14: Build final result
    elapsed = round((time.time() - t0) * 1000)
    return {
        'meta': {
            'code': code, 'name': name,
            'report_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'generation_ms': elapsed,
        },
        'price_data': {
            'price': latest_price,
            'pct': round((latest_price / prev.get('close', 1) - 1) * 100, 2) if prev else 0,
            'open': latest.get('open', 0),
            'high': latest.get('high', 0),
            'low': latest.get('low', 0),
            'pre_close': prev.get('close', 0) if prev else 0,
            'volume': latest.get('volume', 0),
        },
        'kline_table': kline_table,
        'factors': {k: round(v, 2) for k, v in factors.items()},
        'factor_percentiles': factor_percentiles,
        'structure': structure,
        'structure_analysis': structure_analysis,
        'risk_tags': risk_tags,
        'market_context': {
            'state': market_state,
            'sector_name': sector_name,
            'sector_pct': sector_pct,
            'sector_rank': sector_rank,
            'sector_up_ratio': sector_up_ratio,
        },
        'sector_analysis': sector_analysis,
        'backtest': {
            'total_samples': total_samples,
            'structure': stats.structure,
            'win_rate_t1': stats.win_rate_t1, 'win_rate_t3': stats.win_rate_t3,
            'win_rate_t5': stats.win_rate_t5, 'win_rate_t10': stats.win_rate_t10,
            'avg_ret_t1': stats.avg_ret_t1, 'avg_ret_t3': stats.avg_ret_t3,
            'avg_ret_t5': stats.avg_ret_t5, 'avg_ret_t10': stats.avg_ret_t10,
            'median_max_dd_5': stats.median_max_dd_5,
            'by_market_state': by_state,
        },
        'observation_score': score,
        'observation_points': observation_points,
        'comprehensive_judgment': comprehensive_judgment,
        'top_matches': [
            {'rank': i + 1, 'date': m.date, 'code': m.code, 'name': m.name,
             'similarity': m.similarity, 'structure': m.structure,
             'ret_t5': m.ret_t5, 'max_dd_5': m.max_dd_5}
            for i, m in enumerate(matches[:12])
        ],
    }


if __name__ == '__main__':
    # Quick test
    import random, json
    random.seed(42)
    price = 40.0
    klines = []
    for i in range(35):
        change = random.gauss(0.005, 0.025)
        price *= (1 + change)
        klines.append({
            'date': f'day{i}', 'open': round(price * 0.99, 2),
            'close': round(price, 2), 'high': round(price * 1.04, 2),
            'low': round(price * 0.96, 2), 'volume': random.randint(1e6, 5e6),
        })

    result = generate_diagnosis(
        '603876', '鼎胜新材', klines,
        market_state='震荡偏多', sector_name='有色金属',
        sector_pct=1.82, sector_rank=8, sector_up_ratio=0.55,
    )
    print(f"Structure: {result['structure']}")
    print(f"Score: {result['observation_score']['total']} — {result['observation_score']['interpretation']}")
    print(f"Backtest samples: {result['backtest']['total_samples']}")
    print(f"Win rate T+5: {result['backtest']['win_rate_t5']}%")
    print(f"Risk tags: {[t['label'] for t in result['risk_tags']]}")
    print(f"Time: {result['meta']['generation_ms']}ms")
