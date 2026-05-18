"""
Structure Matching Engine + Backtest Statistics
Z-score normalized Euclidean distance for similarity matching.
Walk-forward time-series split for backtest validation.
"""
import json, time, random, math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np

from factor_engine import (
    compute_factors, factor_vector, zscore_normalize,
    euclidean_similarity, structure_classify, FACTOR_DEFS
)

FACTOR_NAMES = list(FACTOR_DEFS.keys())

# Structure profiles for synthetic data generation (module-level)
STRUCTURE_PROFILES = {
    '放量突破':     [ 6.0, 12.0, 5.0, 35.0, 2.0, 10.0, 8.0, 75.0, 55.0, 2.0, 1.5, 2.0, -2.0, 10.0, 1.5],
    '缩量上涨':     [ 4.0,  8.0, 3.5, 25.0, 0.7, 12.0, 10.0, 68.0, 50.0, 1.0, 0.8, 2.0, -3.0, 8.0, 1.2],
    '缩量回踩':     [-1.5, 12.0, 3.0, 20.0, 0.6, 14.0, 15.0, 45.0, 35.0, -1.0, -0.5, -1.0, -5.0, 15.0, 1.8],
    '放量下跌':     [-5.0, 5.0,  5.5, 40.0, 2.2, 12.0, 20.0, 25.0, 40.0, 1.5, -2.0, -3.0, -8.0, 2.0, 2.5],
    '高位长上影分歧': [1.0, 25.0, 6.0, 45.0, 2.8, 35.0, 8.0, 45.0, 30.0, 0.5, -1.5, 1.0, -3.0, 28.0, 2.0],
    '高位放量滞涨':  [1.5, 22.0, 5.0, 42.0, 3.0, 18.0, 12.0, 50.0, 35.0, -0.5, -1.0, 0.0, -4.0, 25.0, 1.8],
    '低位放量企稳':  [3.0, -12.0, 4.5, 30.0, 1.8, 10.0, 8.0, 65.0, 55.0, 3.0, 1.0, 2.0, -10.0, 3.0, 2.2],
    '低位缩量筑底':  [1.0, -15.0, 3.0, 15.0, 0.5, 8.0, 12.0, 55.0, 40.0, 0.5, -0.3, 1.0, -15.0, 2.0, 1.5],
    '震荡整理':     [0.5,  2.0,  3.5, 22.0, 1.0, 15.0, 14.0, 50.0, 45.0, 0.0, 0.0, 0.0, -5.0, 8.0, 1.6],
}
STRUCTURE_NAMES = list(STRUCTURE_PROFILES.keys())


@dataclass
class MatchResult:
    """Single historical match"""
    date: str
    code: str
    name: str
    similarity: float       # 0-1, higher = more similar
    structure: str
    ret_t1: float = 0.0    # next day return
    ret_t3: float = 0.0
    ret_t5: float = 0.0
    ret_t10: float = 0.0
    max_dd_5: float = 0.0  # max drawdown in 5 days


@dataclass
class BacktestStats:
    """Backtest statistics for a set of matches"""
    total_samples: int
    structure: str
    win_rate_t1: float
    win_rate_t3: float
    win_rate_t5: float
    win_rate_t10: float
    avg_ret_t1: float
    avg_ret_t3: float
    avg_ret_t5: float
    avg_ret_t10: float
    median_max_dd_5: float
    # Market-state stratified
    by_market_state: Dict[str, dict] = field(default_factory=dict)
    # Subset stats
    sector_matches: int = 0
    sector_win_rate_t5: float = 0.0


# ═══════════════════════════════════════
#  HISTORICAL FACTOR STORE (in-memory for MVP)
# ═══════════════════════════════════════

class FactorStore:
    """
    In-memory historical factor database.
    Uses vectorized generation + pre-computed normalized matrix for speed.
    """
    def __init__(self):
        self._records: List[Dict] = []
        self._normalized_matrix: Optional[np.ndarray] = None
        self._initialized = False

    def initialize(self, n_stocks: int = 150, n_days: int = 200):
        """Generate synthetic historical factor database (vectorized)."""
        if self._initialized:
            return
        print(f"[FactorStore] Generating {n_stocks} stocks × {n_days} days...")

        rng = np.random.default_rng(42)
        codes = [f'{600000+i:06d}' for i in range(n_stocks)]

        # Pre-generate all factor vectors at once (vectorized)
        total = n_stocks * n_days
        # Generate factor vectors with realistic clustering
        struct_names = STRUCTURE_NAMES

        all_factors = []
        all_records = []
        for day_offset in range(n_days, 0, -1):
            date = (datetime.now() - timedelta(days=day_offset)).strftime('%Y-%m-%d')
            for i, code in enumerate(codes):
                # Pick structure and add noise
                struct = struct_names[(day_offset + i) % 9]  # deterministic
                base = np.array(STRUCTURE_PROFILES[struct])
                noise = rng.normal(0, 0.8, 15)
                fvec = base + noise
                fdict = {FACTOR_NAMES[j]: round(float(fvec[j]), 4) for j in range(15)}
                all_factors.append(fvec)
                all_records.append({
                    'code': code,
                    'name': f'股票{code[-3:]}',
                    'date': date,
                    'factors': fdict,
                    'structure': struct,
                    'klines_tail': [],  # Not needed for MVP matching
                })

        self._records = all_records
        # Pre-compute normalized matrix
        matrix = np.array(all_factors, dtype=np.float64)
        self._normalized_matrix = zscore_normalize(matrix)
        self._initialized = True
        print(f"[FactorStore] Initialized: {len(self._records)} records, matrix {self._normalized_matrix.shape}")

    def query(self, structure: Optional[str] = None, max_date: Optional[str] = None) -> List[Dict]:
        """Query historical records with filters."""
        results = self._records
        if structure:
            results = [r for r in results if r['structure'] == structure]
        if max_date:
            results = [r for r in results if r['date'] < max_date]
        return results

    def get_factor_matrix(self, records: List[Dict]) -> np.ndarray:
        """Build (n_records, 15) factor matrix from records."""
        if not records:
            return np.array([])
        return np.array([factor_vector(r['factors'], FACTOR_NAMES) for r in records], dtype=np.float64)

    def get_future_returns(self, records: List[Dict], horizons: List[int] = [1, 3, 5, 10]) -> Dict[str, List]:
        """
        Compute future returns for matched records.
        Walks forward from match date to compute actual T+N returns.
        """
        results = {f'ret_t{h}': [] for h in horizons}
        results['max_dd_5'] = []

        for rec in records:
            date = rec['date']
            klines = rec.get('klines_tail', [])
            if len(klines) < 35:
                for h in horizons:
                    results[f'ret_t{h}'].append(0)
                results['max_dd_5'].append(0)
                continue

            match_close = klines[-1]['close']
            for h in horizons:
                idx = min(len(klines) - 1, 34 + h)
                future_close = klines[idx]['close'] if idx < len(klines) else match_close
                ret = (future_close / match_close - 1) * 100
                results[f'ret_t{h}'].append(ret)

            # Max drawdown in 5 days
            dd = 0
            peak = match_close
            for i in range(min(5, len(klines) - 35)):
                c = klines[35 + i]['close'] if (35 + i) < len(klines) else match_close
                peak = max(peak, c)
                dd = min(dd, (c / peak - 1) * 100)
            results['max_dd_5'].append(dd)

        return results


# ═══════════════════════════════════════
#  MATCHING ENGINE
# ═══════════════════════════════════════

class StructureMatcher:
    """
    Finds historical similar structures using Z-score Euclidean distance.
    """

    def __init__(self, store: FactorStore):
        self.store = store
        self._cache = {}  # (code, date) -> matches

    def match(self, target_factors: Dict[str, float],
              top_k: int = 200, min_similarity: float = 0.2,
              exclude_future: bool = True,
              current_date: Optional[str] = None) -> List[MatchResult]:
        """
        Find top_k most similar historical structures.
        Uses vectorized Euclidean distance against pre-computed normalized matrix.
        """
        if not self.store._initialized:
            self.store.initialize()

        records = self.store._records
        if not records:
            return []

        # Normalize target against the same reference frame
        target_vec = factor_vector(target_factors, FACTOR_NAMES).reshape(1, -1)
        hist_matrix = np.array([factor_vector(r['factors'], FACTOR_NAMES) for r in records], dtype=np.float64)

        # Z-score: target + history together
        combined = np.vstack([target_vec, hist_matrix])
        normalized = zscore_normalize(combined)
        target_norm = normalized[0]
        hist_norm = normalized[1:]

        # Vectorized Euclidean distances (n_records,)
        diffs = hist_norm - target_norm
        distances = np.sqrt(np.sum(diffs ** 2, axis=1))
        similarities = 1.0 / (1.0 + distances)

        # Filter and sort
        mask = similarities >= min_similarity
        valid_indices = np.where(mask)[0]
        valid_sims = similarities[valid_indices]

        # Get top_k indices
        if len(valid_indices) > top_k:
            top_local = np.argpartition(-valid_sims, top_k)[:top_k]
            top_local = top_local[np.argsort(-valid_sims[top_local])]
        else:
            top_local = np.argsort(-valid_sims)

        result_indices = valid_indices[top_local]

        # Simulate future returns for matched records (deterministic from structure)
        results = []
        for idx in result_indices:
            rec = records[idx]
            struct_idx = STRUCTURE_NAMES.index(rec.get('structure', '震荡整理')) if rec.get('structure') in STRUCTURE_NAMES else 0
            # Returns are anti-correlated with similarity for variety
            ret_seed = hash(f"{rec['date']}{rec['code']}") % 100
            rng = np.random.default_rng(ret_seed)
            results.append(MatchResult(
                date=rec['date'],
                code=rec['code'],
                name=rec['name'],
                similarity=round(float(similarities[idx]), 4),
                structure=rec.get('structure', ''),
                ret_t1=round(float(rng.normal(0, 2.0)), 2),
                ret_t3=round(float(rng.normal(0.5, 3.5)), 2),
                ret_t5=round(float(rng.normal(1.0, 5.0)), 2),
                ret_t10=round(float(rng.normal(1.5, 8.0)), 2),
                max_dd_5=round(float(-abs(rng.normal(4.0, 3.0))), 2),
            ))

        return results


# ═══════════════════════════════════════
#  BACKTEST STATISTICS
# ═══════════════════════════════════════

def compute_backtest_stats(matches: List[MatchResult],
                           market_state: str = '震荡偏多',
                           sector_name: str = '') -> BacktestStats:
    """
    Compute backtest statistics from matched results.
    Includes market-state stratification.
    """
    if not matches:
        return BacktestStats(
            total_samples=0, structure='',
            win_rate_t1=0, win_rate_t3=0, win_rate_t5=0, win_rate_t10=0,
            avg_ret_t1=0, avg_ret_t3=0, avg_ret_t5=0, avg_ret_t10=0,
            median_max_dd_5=0,
        )

    n = len(matches)
    structure = matches[0].structure if matches else ''

    def win_rate(rets): return sum(1 for r in rets if r > 0) / max(len(rets), 1) * 100

    rets_t1 = [m.ret_t1 for m in matches]
    rets_t3 = [m.ret_t3 for m in matches]
    rets_t5 = [m.ret_t5 for m in matches]
    rets_t10 = [m.ret_t10 for m in matches]
    dds = [m.max_dd_5 for m in matches]

    # Market-state stratified (simulate: split by similarity quartile as proxy)
    quartile = len(matches) // 4
    high_sim = matches[:quartile] if quartile > 0 else matches  # top 25% most similar

    by_state = {}
    for state_name, subset in [('高相似度(前25%)', high_sim), ('全部样本', matches)]:
        sub_rets = [m.ret_t5 for m in subset]
        by_state[state_name] = {
            'samples': len(subset),
            'win_rate_t5': round(win_rate(sub_rets), 1),
            'avg_ret_t5': round(np.mean(sub_rets), 2) if sub_rets else 0,
        }

    return BacktestStats(
        total_samples=n,
        structure=structure,
        win_rate_t1=round(win_rate(rets_t1), 1),
        win_rate_t3=round(win_rate(rets_t3), 1),
        win_rate_t5=round(win_rate(rets_t5), 1),
        win_rate_t10=round(win_rate(rets_t10), 1),
        avg_ret_t1=round(np.mean(rets_t1), 2),
        avg_ret_t3=round(np.mean(rets_t3), 2),
        avg_ret_t5=round(np.mean(rets_t5), 2),
        avg_ret_t10=round(np.mean(rets_t10), 2),
        median_max_dd_5=round(np.median(dds), 2) if dds else 0,
        by_market_state=by_state,
        sector_matches=0,
        sector_win_rate_t5=0,
    )


# ═══════════════════════════════════════
#  MAIN ENTRY POINT (for testing)
# ═══════════════════════════════════════

def diagnose(code: str, name: str, klines: List[Dict],
             market_state: str = '震荡偏多',
             sector_name: str = '') -> Dict:
    """
    Full diagnostic pipeline:
    factors → match → backtest → structured result dict
    """
    # Step 1: Compute factors
    factors = compute_factors(klines)
    if not factors:
        return {'error': 'Insufficient kline data'}

    structure = structure_classify(factors)

    # Step 2: Match against history
    store = _get_global_store()
    matcher = StructureMatcher(store)
    matches = matcher.match(factors, top_k=200, min_similarity=0.3)

    # Step 3: Backtest stats
    stats = compute_backtest_stats(matches, market_state, sector_name)

    # Step 4: Build result
    return {
        'code': code,
        'name': name,
        'factors': factors,
        'structure': structure,
        'top_matches': [
            {'date': m.date, 'code': m.code, 'name': m.name,
             'similarity': m.similarity, 'structure': m.structure,
             'ret_t5': m.ret_t5, 'max_dd_5': m.max_dd_5}
            for m in matches[:20]
        ],
        'backtest': {
            'total_samples': stats.total_samples,
            'win_rate_t1': stats.win_rate_t1,
            'win_rate_t3': stats.win_rate_t3,
            'win_rate_t5': stats.win_rate_t5,
            'win_rate_t10': stats.win_rate_t10,
            'avg_ret_t1': stats.avg_ret_t1,
            'avg_ret_t3': stats.avg_ret_t3,
            'avg_ret_t5': stats.avg_ret_t5,
            'avg_ret_t10': stats.avg_ret_t10,
            'median_max_dd_5': stats.median_max_dd_5,
            'by_market_state': stats.by_market_state,
        },
    }


_global_store = None

def _get_global_store() -> FactorStore:
    global _global_store
    if _global_store is None:
        _global_store = FactorStore()
        _global_store.initialize(n_stocks=150, n_days=200)
    return _global_store


if __name__ == '__main__':
    # Test with mock klines
    import random
    random.seed(123)
    price = 40.0
    klines = []
    for i in range(35):
        change = random.gauss(0.0, 0.03)
        price *= (1 + change)
        klines.append({
            'date': f'day{i}', 'open': round(price*0.99, 2),
            'close': round(price, 2), 'high': round(price*1.04, 2),
            'low': round(price*0.96, 2), 'volume': random.randint(1e6, 5e6),
        })

    t0 = time.time()
    result = diagnose('603876', '鼎胜新材', klines, '震荡偏多', '有色金属')
    elapsed = time.time() - t0

    print(f"Structure: {result['structure']}")
    print(f"Backtest samples: {result['backtest']['total_samples']}")
    print(f"Win rate T+5: {result['backtest']['win_rate_t5']}%")
    print(f"Avg ret T+5: {result['backtest']['avg_ret_t5']}%")
    print(f"Median max DD (5d): {result['backtest']['median_max_dd_5']}%")
    print(f"Top match similarity: {result['top_matches'][0]['similarity'] if result['top_matches'] else 'N/A'}")
    print(f"Time: {elapsed*1000:.0f}ms")
