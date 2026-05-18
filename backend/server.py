"""
A股异动复盘助手 — Flask Backend
Primary: Direct Eastmoney API  |  Fallback: Realistic mock data
"""
import json, time, random, re, requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from report_engine import generate_diagnosis
try:
    from data_fetcher import fetch_klines, search_stocks_bs
except ImportError:
    fetch_klines = None
    search_stocks_bs = None
try:
    from live_data import get_live_gainers, get_live_volume_anomaly, get_live_indices
except ImportError:
    get_live_gainers = None
    get_live_volume_anomaly = None
    get_live_indices = None

app = Flask(__name__)
CORS(app)

cache, cache_ttl = {}, {}

def cached(key, ttl=15):
    def decorator(fn):
        def wrapper(*a, **kw):
            now = time.time()
            if key in cache and now - cache_ttl.get(key, 0) < ttl:
                return cache[key]
            result = fn(*a, **kw)
            cache[key] = result
            cache_ttl[key] = now
            return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


# ═══════════════════════════════════════
#  EASTMONEY API (primary)
# ═══════════════════════════════════════

EM_BASE = 'https://push2.eastmoney.com/api/qt/clist/get'
EM_HIST = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
EM_AVAILABLE = False  # set True when Eastmoney API is reachable

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
})

def em_get(url=EM_BASE, **params):
    global EM_AVAILABLE
    if not EM_AVAILABLE:
        return None
    defaults = {
        'pn': '1', 'pz': '5000', 'po': '1', 'np': '1',
        'fltt': '2', 'invt': '2', 'dect': '1',
        'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21',
    }
    defaults.update(params)
    try:
        r = SESSION.get(url, params=defaults, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    EM_AVAILABLE = False
    return None


def em_spot(market='all'):
    market_map = {
        'all': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
        'sh': 'm:1+t:2,m:1+t:23',
        'sz': 'm:0+t:6,m:0+t:80',
    }
    return em_get(fs=market_map.get(market, market_map['all']), pz='5500')


def em_indices():
    return em_get(fs='b:1+b:2', pz='10')


def em_sectors(type='industry'):
    fs = 'm:90+t:2' if type == 'industry' else 'm:90+t:3'
    return em_get(fs=fs, pz='50', po='1')


def em_kline(code, days=30):
    secid = f'1.{code}' if code.startswith(('6','5')) else f'0.{code}'
    return em_get(url=EM_HIST, secid=secid, klt='101', fqt='1', end='20500101', lmt=str(days),
                  fields='f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21')


def parse_spot(diff):
    return {
        'code': str(diff.get('f12', '')), 'name': str(diff.get('f14', '')),
        'price': float(diff.get('f2', 0) or 0), 'pct': float(diff.get('f3', 0) or 0),
        'open': float(diff.get('f17', 0) or 0), 'high': float(diff.get('f15', 0) or 0),
        'low': float(diff.get('f16', 0) or 0), 'pre_close': float(diff.get('f18', 0) or 0),
        'volume': float(diff.get('f5', 0) or 0), 'amount': float(diff.get('f6', 0) or 0),
        'turnover': float(diff.get('f8', 0) or 0), 'volume_ratio': float(diff.get('f10', 0) or 0),
        'pe': float(diff.get('f9', 0) or 0), 'total_mv': float(diff.get('f20', 0) or 0),
        'circ_mv': float(diff.get('f21', 0) or 0),
    }


# ═══════════════════════════════════════
#  MOCK DATA GENERATOR (fallback)
# ═══════════════════════════════════════

# 150 realistic A-share stock names
STOCK_POOL = [
    ('600519', '贵州茅台', 1680.0, 28.5), ('000858', '五粮液', 148.5, 22.3),
    ('601318', '中国平安', 42.8, 8.5), ('000333', '美的集团', 68.2, 14.2),
    ('600036', '招商银行', 38.5, 5.8), ('601398', '工商银行', 5.68, 5.1),
    ('000651', '格力电器', 38.2, 10.3), ('002415', '海康威视', 36.8, 24.5),
    ('300750', '宁德时代', 210.5, 38.2), ('002594', '比亚迪', 268.0, 32.1),
    ('601012', '隆基绿能', 18.6, 15.8), ('600900', '长江电力', 29.8, 22.5),
    ('600030', '中信证券', 21.5, 14.2), ('000001', '平安银行', 10.8, 5.5),
    ('601899', '紫金矿业', 18.2, 15.0), ('600809', '山西汾酒', 198.0, 28.8),
    ('002714', '牧原股份', 42.5, 12.3), ('601166', '兴业银行', 17.2, 4.5),
    ('600276', '恒瑞医药', 48.5, 58.0), ('300760', '迈瑞医疗', 285.0, 35.5),
    ('600887', '伊利股份', 27.8, 18.5), ('603259', '药明康德', 52.5, 22.0),
    ('002475', '立讯精密', 32.8, 25.5), ('300059', '东方财富', 22.5, 42.0),
    ('601888', '中国中免', 72.5, 28.0), ('000725', '京东方A', 4.35, 30.5),
    ('002230', '科大讯飞', 48.5, 85.0), ('688981', '中芯国际', 58.2, 45.5),
    ('688388', '嘉元科技', 38.5, 35.0), ('688005', '容百科技', 42.0, 30.0),
    ('688012', '中微公司', 185.0, 68.0), ('688111', '金山办公', 425.0, 85.0),
    ('688036', '传音控股', 128.0, 22.0), ('688561', '奇安信', 32.5, -1.0),
    ('688169', '石头科技', 325.0, 28.5), ('688008', '澜起科技', 72.5, 58.0),
    ('688256', '寒武纪', 285.0, -1.0), ('688396', '华润微', 45.8, 38.0),
    ('601688', '华泰证券', 16.5, 12.8), ('300124', '汇川技术', 68.5, 38.0),
    ('000568', '泸州老窖', 168.0, 20.5), ('002142', '宁波银行', 25.8, 7.2),
    ('600048', '保利发展', 9.8, 8.5), ('601919', '中远海控', 14.8, 5.2),
    ('002352', '顺丰控股', 42.8, 32.5), ('300274', '阳光电源', 88.5, 42.0),
    ('600585', '海螺水泥', 22.5, 12.0), ('000063', '中兴通讯', 32.8, 18.5),
    ('601857', '中国石油', 8.85, 7.5), ('600028', '中国石化', 5.65, 6.8),
    ('002371', '北方华创', 385.0, 55.0), ('688111', '金山办公', 425.0, 85.0),
    ('300502', '新易盛', 125.0, 65.0), ('601138', '工业富联', 28.5, 22.0),
    ('603019', '中科曙光', 58.5, 48.0), ('002049', '紫光国微', 72.0, 35.5),
    ('300308', '中际旭创', 168.0, 72.0), ('688256', '寒武纪', 285.0, -1.0),
    ('000977', '浪潮信息', 45.8, 32.0), ('600745', '闻泰科技', 38.2, 28.5),
    ('601615', '明阳智能', 12.8, 18.0), ('688012', '中微公司', 185.0, 68.0),
    ('300450', '先导智能', 22.5, 25.0), ('002460', '赣锋锂业', 32.8, 15.5),
    ('600438', '通威股份', 28.5, 8.2), ('601225', '陕西煤业', 25.8, 6.5),
    ('000002', '万科A', 8.25, 7.8), ('001979', '招商蛇口', 9.85, 18.5),
    ('600031', '三一重工', 18.2, 22.0), ('000425', '徐工机械', 7.85, 15.5),
    ('603986', '兆易创新', 98.5, 45.0), ('603876', '鼎胜新材', 30.0, 25.0),
    ('002241', '歌尔股份', 22.8, 28.5),
    ('300433', '蓝思科技', 18.5, 32.0), ('601728', '中国电信', 7.25, -1.0),
    ('600050', '中国联通', 5.85, -1.0), ('600941', '中国移动', 108.5, 16.5),
    ('688396', '华润微', 45.8, 38.0), ('300782', '卓胜微', 85.0, 55.0),
    ('002916', '深南电路', 128.0, 35.5), ('603501', '韦尔股份', 128.5, 42.0),
    ('688008', '澜起科技', 72.5, 58.0), ('300661', '圣邦股份', 88.5, 65.0),
    ('601100', '恒立液压', 58.5, 32.0), ('600406', '国电南瑞', 25.8, 28.5),
    ('002074', '国轩高科', 22.5, 85.0), ('300014', '亿纬锂能', 48.5, 32.0),
    ('601689', '拓普集团', 58.5, 35.0), ('002920', '德赛西威', 128.0, 48.0),
    ('300496', '中科创达', 52.5, 42.0), ('688561', '奇安信', 32.5, -1.0),
    ('002410', '广联达', 28.5, 55.0), ('600570', '恒生电子', 38.5, 42.0),
    ('300033', '同花顺', 125.0, 45.0), ('603160', '汇顶科技', 58.5, 38.0),
    ('688169', '石头科技', 325.0, 28.5), ('300413', '芒果超媒', 28.5, 32.0),
    ('002555', '三七互娱', 18.5, 15.0), ('603444', '吉比特', 285.0, 18.5),
    ('601066', '中信建投', 25.8, 28.0), ('600837', '海通证券', 9.85, 22.5),
    ('000776', '广发证券', 15.8, 15.5), ('601211', '国泰君安', 15.2, 12.8),
    ('002736', '国信证券', 10.5, 18.0), ('300803', '指南针', 85.0, 68.0),
    ('601878', '浙商证券', 12.5, 22.0), ('600999', '招商证券', 15.8, 15.5),
]

# Sector mapping
SECTOR_MAP = {
    '白酒': ['贵州茅台', '五粮液', '泸州老窖', '山西汾酒'],
    '银行': ['招商银行', '工商银行', '兴业银行', '平安银行', '宁波银行'],
    '保险证券': ['中国平安', '中信证券', '华泰证券', '东方财富', '同花顺'],
    '新能源': ['宁德时代', '隆基绿能', '阳光电源', '赣锋锂业', '亿纬锂能', '通威股份'],
    '半导体': ['中芯国际', '北方华创', '韦尔股份', '澜起科技', '兆易创新', '中微公司', '寒武纪'],
    'AI算力': ['工业富联', '中科曙光', '浪潮信息', '中际旭创', '新易盛', '金山办公'],
    '汽车': ['比亚迪', '拓普集团', '德赛西威', '先导智能', '国轩高科'],
    '医药': ['恒瑞医药', '迈瑞医疗', '药明康德', '爱尔眼科'],
    '家电': ['美的集团', '格力电器', '海尔智家'],
    '消费电子': ['立讯精密', '歌尔股份', '蓝思科技'],
    '通信': ['中兴通讯', '中国移动', '中国联通', '中国电信'],
    '煤炭石油': ['陕西煤业', '中国石油', '中国石化', '中国神华'],
    '地产': ['万科A', '保利发展', '招商蛇口'],
    '光伏': ['隆基绿能', '通威股份', '阳光电源'],
    '软件': ['恒生电子', '广联达', '中科创达', '奇安信'],
    '食品饮料': ['贵州茅台', '五粮液', '伊利股份', '泸州老窖', '山西汾酒', '海天味业'],
    '有色金属': ['紫金矿业', '赣锋锂业', '华友钴业', '嘉元科技'],
    '国防军工': ['中航沈飞', '航发动力', '中航西飞'],
    '电力': ['长江电力', '华能水电', '中国核电'],
    '机械': ['三一重工', '恒立液压', '徐工机械'],
    '有色金属': ['紫金矿业', '赣锋锂业', '华友钴业', '鼎胜新材', '嘉元科技'],
    '锂电池': ['宁德时代', '亿纬锂能', '赣锋锂业', '先导智能', '嘉元科技', '鼎胜新材', '容百科技'],
    '科创板': ['中芯国际', '中微公司', '金山办公', '澜起科技', '寒武纪', '嘉元科技', '容百科技'],
    '铝业': ['鼎胜新材', '中国铝业', '南山铝业', '明泰铝业'],
}

# Market state
_market_state = {
    'sh_idx': 4120.0, 'sz_idx': 15480.0, 'cy_idx': 2510.0,
    'hs300_idx': 3980.0, 'zz500_idx': 6250.0, 'zz1000_idx': 6850.0,
    'kc50_idx': 1020.0, 'sz50_idx': 2720.0,
    'sc50_idx': 1280.0, 'zzhl_idx': 5100.0,
    'sector_bias': random.choice(['AI算力', '新能源', '白酒', '半导体', '汽车', '医药']),
}

INDEX_CONFIG = [
    {'key': 'sh_idx',       'name': '上证指数',   'base': 4120,  'vol': 0.8},
    {'key': 'sz_idx',       'name': '深证成指',   'base': 15480, 'vol': 1.2},
    {'key': 'cy_idx',       'name': '创业板指',   'base': 2510,  'vol': 1.5},
    {'key': 'hs300_idx',    'name': '沪深300',    'base': 3980,  'vol': 0.7},
    {'key': 'zz500_idx',    'name': '中证500',    'base': 6250,  'vol': 1.1},
    {'key': 'zz1000_idx',   'name': '中证1000',   'base': 6850,  'vol': 1.3},
    {'key': 'kc50_idx',     'name': '科创50',     'base': 1020,  'vol': 1.8},
    {'key': 'sz50_idx',     'name': '上证50',     'base': 2720,  'vol': 0.7},
    {'key': 'sc50_idx',     'name': '双创50',     'base': 1280,  'vol': 1.6},
    {'key': 'zzhl_idx',     'name': '中证红利',   'base': 5100,  'vol': 0.5},
]


def _update_market_state():
    ms = _market_state
    for ic in INDEX_CONFIG:
        k = ic['key']
        pct = random.gauss(0, ic['vol'])
        ms[k] = round(ms.get(k, ic['base']) * (1 + pct / 100), 2)


def _gen_mock_stocks():
    """Generate realistic mock stock data"""
    _update_market_state()
    ms = _market_state
    stocks = []
    for code, name, base_price, base_pe in STOCK_POOL:
        # Determine stock's sector
        sector = '其他'
        for sname, members in SECTOR_MAP.items():
            if name in members:
                sector = sname
                break

        # Sector bias for hot sectors
        bias = 0
        if sector == ms['sector_bias']:
            bias = random.uniform(1.0, 4.0)
        elif sector in ['AI算力', '半导体'] and ms['sector_bias'] in ['AI算力', '半导体']:
            bias = random.uniform(0.5, 2.5)

        pct = round(random.gauss(bias, 2.5), 2)
        pct = max(-10.0, min(10.0, pct))
        price = round(base_price * (1 + random.uniform(-0.15, 0.25)), 2)
        price = round(price * (1 + pct / 100), 2)

        turnover = round(random.uniform(0.5, 8.0), 2)
        vol_ratio = round(random.uniform(0.3, 4.5), 2)
        amount = round(random.uniform(1e7, 5e9), 0)

        # Hot sector gets more volume
        if sector == ms['sector_bias']:
            turnover = round(random.uniform(3.0, 25.0), 2)
            vol_ratio = round(random.uniform(1.5, 6.0), 2)

        stocks.append({
            'code': code, 'name': name, 'price': price, 'pct': pct,
            'open': round(base_price * random.uniform(0.97, 1.03), 2),
            'high': round(price * random.uniform(1.0, 1.05), 2),
            'low': round(price * random.uniform(0.95, 1.0), 2),
            'pre_close': round(base_price, 2),
            'volume': random.randint(50000, 50000000),
            'amount': amount, 'turnover': turnover,
            'volume_ratio': vol_ratio,
            'pe': base_pe if base_pe > 0 else random.uniform(-200, -10),
            'total_mv': round(random.uniform(5e9, 5e11), 0),
            'circ_mv': round(random.uniform(2e9, 2e11), 0),
        })

    # Add some 涨停 stocks
    for _ in range(random.randint(3, 10)):
        s = random.choice(stocks)
        s['pct'] = round(random.uniform(9.95, 10.02), 2)
        s['turnover'] = round(random.uniform(5, 28), 2)
        s['volume_ratio'] = round(random.uniform(1.8, 5.5), 2)
        s['price'] = round(s['pre_close'] * (1 + s['pct'] / 100), 2)

    return stocks


def _gen_mock_sectors(stype='industry'):
    industry_sectors = [
        '白酒', '食品饮料', '半导体', 'AI算力', '新能源', '锂电池', '汽车', '医药', '银行',
        '保险证券', '家电', '消费电子', '通信设备', '光伏', '软件服务',
        '煤炭石油', '地产', '国防军工', '有色金属', '电力', '机械', '科创板', '铝业',
    ]
    concept_sectors = [
        'ChatGPT概念', 'AIGC', 'CPO', '液冷服务器', '华为产业链',
        'Chiplet', '存储芯片', '自动驾驶', '固态电池', '人形机器人',
        '低空经济', '量子计算', '东数西算', '信创', '智能电网',
    ]
    pool = industry_sectors if stype == 'industry' else concept_sectors
    result = []
    ms = _market_state
    for i, name in enumerate(pool[:20]):
        pct = round(random.uniform(-2.5, 5.0), 2)
        if name == ms['sector_bias'] or name in ['AI算力', '半导体']:
            pct = round(random.uniform(1.5, 6.5), 2)
        leader_name = random.choice([s[1] for s in STOCK_POOL])
        result.append({
            'name': name, 'pct': pct,
            'leader': leader_name,
            'leader_pct': round(random.uniform(3.0, 10.0), 2),
            'up_count': random.randint(5, 40) if pct > 0 else random.randint(1, 15),
            'down_count': random.randint(1, 15) if pct > 0 else random.randint(5, 40),
        })
    result.sort(key=lambda x: x['pct'], reverse=True)
    return result


def _gen_mock_indices():
    ms = _market_state
    return [{'key': ic['key'], 'name': ic['name'], 'price': round(ms.get(ic['key'], ic['base']), 2)}
            for ic in INDEX_CONFIG]


def compute_risk_tags(stock):
    tags = []
    pct = float(stock.get('pct', 0) or 0)
    turnover = float(stock.get('turnover', 0) or 0)
    vol_ratio = float(stock.get('volume_ratio', 0) or 0)

    if pct >= 9.5: tags.append({'label': '涨停', 'type': 'danger'})
    elif pct >= 7: tags.append({'label': '大涨', 'type': 'warning'})
    if turnover > 20: tags.append({'label': '超高换手', 'type': 'danger'})
    elif turnover > 10: tags.append({'label': '高换手', 'type': 'warning'})
    if vol_ratio > 3: tags.append({'label': '巨量', 'type': 'danger'})
    elif vol_ratio > 2: tags.append({'label': '放量', 'type': 'warning'})
    if pct >= 5 and turnover > 15: tags.append({'label': '题材炒作', 'type': 'warning'})
    if pct >= 9.5 and turnover > 25: tags.append({'label': '不适合追高', 'type': 'danger'})
    if pct >= 7 and vol_ratio > 3: tags.append({'label': '只适合观察', 'type': 'info'})
    if not tags: tags.append({'label': '正常', 'type': 'info'})
    return tags


# ═══════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════

@app.route('/api/market')
def api_market():
    # Try real baostock indices first
    if get_live_indices:
        try:
            live = get_live_indices()
            if live and len(live) >= 3:
                return jsonify(live)
        except:
            pass
    return jsonify(_gen_mock_indices())


@app.route('/api/gainers')
def api_gainers():
    if get_live_gainers:
        try:
            live = get_live_gainers(30)
            if live and len(live) >= 5:
                for s in live:
                    s['risk_tags'] = compute_risk_tags(s)
                return jsonify(live)
        except Exception as e:
            print(f'Live gainers error: {e}')
    stocks = _gen_mock_stocks()
    stocks.sort(key=lambda x: x['pct'], reverse=True)
    for s in stocks[:30]:
        s['risk_tags'] = compute_risk_tags(s)
    return jsonify(stocks[:30])


@app.route('/api/sectors')
def api_sectors():
    global EM_AVAILABLE
    ind_list, con_list = [], []
    if EM_AVAILABLE:
        try:
            ind = em_sectors('industry')
            con = em_sectors('concept')
            for d in ind.get('data', {}).get('diff', [])[:20]:
                ind_list.append({
                    'name': str(d.get('f14', '')), 'pct': round(float(d.get('f3', 0) or 0), 2),
                    'leader': str(d.get('f128', '')), 'leader_pct': round(float(d.get('f136', 0) or 0), 2),
                    'up_count': int(d.get('f104', 0) or 0), 'down_count': int(d.get('f105', 0) or 0),
                })
            for d in con.get('data', {}).get('diff', [])[:15]:
                con_list.append({
                    'name': str(d.get('f14', '')), 'pct': round(float(d.get('f3', 0) or 0), 2),
                    'leader': str(d.get('f128', '')), 'leader_pct': round(float(d.get('f136', 0) or 0), 2),
                })
            if ind_list:
                return jsonify({'industry': ind_list, 'concept': con_list})
        except:
            pass
    return jsonify({'industry': _gen_mock_sectors('industry'), 'concept': _gen_mock_sectors('concept')})


@app.route('/api/volume')
def api_volume():
    if get_live_volume_anomaly:
        try:
            live = get_live_volume_anomaly(20)
            if live and len(live) >= 5:
                for s in live:
                    s['risk_tags'] = compute_risk_tags(s)
                return jsonify(live)
        except Exception as e:
            print(f'Live volume error: {e}')
    stocks = _gen_mock_stocks()
    vol = [s for s in stocks if s['volume_ratio'] > 1.2]
    vol.sort(key=lambda x: x['volume_ratio'], reverse=True)
    for s in vol[:20]:
        s['risk_tags'] = compute_risk_tags(s)
    return jsonify(vol[:20])


@app.route('/api/review')
def api_review():
    global EM_AVAILABLE
    try:
        if EM_AVAILABLE:
            try:
                data = em_spot('all')
                if data:
                    stocks = [parse_spot(d) for d in data.get('data', {}).get('diff', [])]
            except:
                stocks = _gen_mock_stocks()
        else:
            stocks = _gen_mock_stocks()

        sectors_raw = json.loads(api_sectors().get_data(as_text=True))
        ind_list = sectors_raw.get('industry', [])[:5]

        up_count = sum(1 for s in stocks if s['pct'] > 0)
        down_count = sum(1 for s in stocks if s['pct'] < 0)
        limit_up = sum(1 for s in stocks if s['pct'] >= 9.5)
        limit_down = sum(1 for s in stocks if s['pct'] <= -9.5)

        if up_count > down_count * 3:
            sentiment, desc = '强势', '市场情绪高涨，赚钱效应明显'
        elif up_count > down_count * 1.5:
            sentiment, desc = '偏强', '市场总体偏强，注意板块轮动'
        elif up_count > down_count:
            sentiment, desc = '震荡偏多', '多空基本平衡，局部机会为主'
        elif down_count > up_count * 3:
            sentiment, desc = '弱势', '市场情绪低迷，注意风险控制'
        elif down_count > up_count * 1.5:
            sentiment, desc = '偏弱', '空方占优，控制仓位'
        else:
            sentiment, desc = '震荡偏空', '弱势震荡，多看少动'

        gainers = sorted(stocks, key=lambda x: x['pct'], reverse=True)[:10]
        risk_stocks = []
        for g in gainers:
            tags = compute_risk_tags(g)
            risk_stocks.append({'code': g['code'], 'name': g['name'], 'pct': g['pct'],
                               'tags': [t['label'] for t in tags]})

        vol_stocks = sorted([s for s in stocks if s['volume_ratio'] > 1.5],
                           key=lambda x: x['volume_ratio'], reverse=True)[:5]
        anomaly = [{'code': v['code'], 'name': v['name'],
                    'volume_ratio': v['volume_ratio'], 'pct': v['pct']} for v in vol_stocks]

        top_names = [s.get('name', '') for s in ind_list[:3]]
        summary = f'今日涨停{limit_up}家，跌停{limit_down}家。上涨{up_count}家，下跌{down_count}家。最强板块：{"、".join(top_names)}。市场情绪：{sentiment}。'

        return jsonify({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'market_breadth': {'up': up_count, 'down': down_count, 'limit_up': limit_up,
                              'limit_down': limit_down, 'ratio': round(up_count / max(down_count, 1), 2)},
            'sentiment': sentiment, 'sentiment_desc': desc,
            'top_sectors': [{'name': s['name'], 'pct': s['pct']} for s in ind_list],
            'risk_stocks': risk_stocks, 'volume_anomaly': anomaly,
            'summary': summary,
        })
    except Exception as e:
        print(f"Review error: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/stock/<code>')
def api_stock_detail(code):
    global EM_AVAILABLE
    stock = None
    if EM_AVAILABLE:
        try:
            data = em_spot('all')
            if data:
                for d in data.get('data', {}).get('diff', []):
                    if d.get('f12') == code:
                        stock = parse_spot(d)
                        break
        except:
            pass

    if not stock:
        stocks = _gen_mock_stocks()
        stock = next((s for s in stocks if s['code'] == code), None)

    if not stock:
        return jsonify({'error': 'Stock not found'}), 404

    stock['risk_tags'] = compute_risk_tags(stock)

    # Generate mock kline
    kline = []
    base = stock['pre_close']
    for i in range(30, 0, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        change = random.gauss(0, 0.02)
        close = round(base * (1 + change), 2)
        open_p = round(close * random.uniform(0.995, 1.005), 2)
        high = round(max(open_p, close) * random.uniform(1.0, 1.03), 2)
        low = round(min(open_p, close) * random.uniform(0.97, 1.0), 2)
        vol = random.randint(500000, 30000000)
        kline.append({'date': day, 'open': open_p, 'close': close, 'high': high, 'low': low, 'volume': vol})
        base = close
    stock['kline'] = kline

    return jsonify(stock)


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '')
    if len(q) < 1:
        return jsonify([])
    # Search: try baostock for real names, fall back to mock pool
    results = []
    seen = set()

    if search_stocks_bs:
        bs_results = search_stocks_bs(q, 15)
        for r in bs_results:
            c = r['code']
            if c not in seen:
                seed = hash(c) % 10000
                rng = random.Random(seed)
                pct = round(rng.uniform(-10, 10), 2)
                p = round(rng.uniform(5, 200), 2)
                results.append({'code': c, 'name': r['name'], 'price': p, 'pct': pct})
                seen.add(c)

    if not results:
        for code, name, price, pe in STOCK_POOL:
            if q in code or q in name:
                pct = round(random.uniform(-8, 10), 2)
                results.append({'code': code, 'name': name, 'price': round(price * random.uniform(0.9, 1.2), 2), 'pct': pct})
                seen.add(code)

        q_clean = q.strip()
        if re.match(r'^\d{6}$', q_clean) and q_clean not in seen:
            seed = hash(q_clean) % 10000
            rng = random.Random(seed)
            price = round(rng.uniform(5, 200), 2)
            pct = round(rng.uniform(-10, 10), 2)
            results.insert(0, {'code': q_clean, 'name': f'股票{q_clean[-4:]}', 'price': price, 'pct': pct})

    return jsonify(results[:20])


@app.route('/api/strategies')
def api_strategies():
    stype = request.args.get('type', 'low_volume_breakout')
    global EM_AVAILABLE
    if EM_AVAILABLE:
        try:
            data = em_spot('all')
            stocks = [parse_spot(d) for d in data.get('data', {}).get('diff', [])] if data else []
        except:
            stocks = _gen_mock_stocks()
    else:
        stocks = _gen_mock_stocks()

    if stype == 'low_volume_breakout':
        result = [s for s in stocks if 2 < s['pct'] < 7 and s['volume_ratio'] > 1.5]
        result.sort(key=lambda x: x['volume_ratio'], reverse=True)
    elif stype == 'sector_leader':
        result = [s for s in stocks if s['pct'] > 5 and s['turnover'] > 5]
        result.sort(key=lambda x: x['pct'], reverse=True)
    elif stype == 'high_dividend':
        result = [s for s in stocks if 0 < s['pe'] < 15 and s['pct'] > 0]
        result.sort(key=lambda x: x['pe'])
    elif stype == 'pullback_stable':
        result = [s for s in stocks if 0.5 < s['pct'] < 3 and 0.8 < s['volume_ratio'] < 1.2]
        result.sort(key=lambda x: x['pct'], reverse=True)
    elif stype == 'strong_breakout':
        result = [s for s in stocks if s['pct'] > 7]
        result.sort(key=lambda x: x['pct'], reverse=True)
    elif stype == 'shrink_then_expand':
        result = [s for s in stocks if s['volume_ratio'] > 2 and s['pct'] > 0]
        result.sort(key=lambda x: x['volume_ratio'], reverse=True)
    else:
        result = []

    return jsonify([{
        'code': r['code'], 'name': r['name'], 'price': r['price'],
        'pct': r['pct'], 'volume_ratio': r['volume_ratio'],
        'turnover': r['turnover'], 'pe': r['pe'],
    } for r in result[:20]])

# ═══════════════════════════════════════
#  DIAGNOSTIC REPORT API
# ═══════════════════════════════════════

@app.route('/api/diagnose/<code>')
def api_diagnose(code):
    """Full diagnostic report for a single stock."""
    # Get spot data
    if EM_AVAILABLE:
        try:
            data = em_spot('all')
            stocks = [parse_spot(d) for d in data.get('data', {}).get('diff', [])] if data else []
        except:
            stocks = _gen_mock_stocks()
    else:
        stocks = _gen_mock_stocks()

    match = next((s for s in stocks if s['code'] == code), None)
    if not match:
        # Try baostock for real name
        real_name = None
        if search_stocks_bs:
            bs_r = search_stocks_bs(code, 1)
            if bs_r and bs_r[0]['code'] == code:
                real_name = bs_r[0]['name']

        seed = hash(code) % 10000
        rng = random.Random(seed)
        match = {
            'code': code,
            'name': real_name or f'股票{code[-4:]}',
            'price': round(rng.uniform(8, 180), 2),
            'pct': round(rng.uniform(-8, 10), 2),
            'pre_close': round(rng.uniform(8, 180), 2),
        }

    # Get kline data
    klines = []
    try:
        kdata = em_kline(code, 35)
        raw_klines = kdata.get('data', {}).get('klines', []) if kdata else []
        for k in raw_klines:
            parts = k.split(',')
            if len(parts) >= 6:
                klines.append({
                    'date': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'volume': float(parts[5]),
                })
    except:
        pass

    if len(klines) < 5:
        # Try real data from baostock first
        if fetch_klines:
            real_klines = fetch_klines(code, 35)
            if real_klines and len(real_klines) >= 5:
                klines = real_klines

    # Get market context
    review_data = {}
    try:
        review_raw = api_review().get_json() if hasattr(api_review(), 'get_json') else {}
        review_data = review_raw if isinstance(review_raw, dict) else {}
    except:
        pass

    market_state = review_data.get('sentiment', '震荡偏多')

    # Get sector info — look up stock's ACTUAL sector from SECTOR_MAP
    stock_name = match.get('name', '')
    actual_sector = None
    for sname, members in SECTOR_MAP.items():
        if stock_name in members:
            actual_sector = sname
            break
    if actual_sector is None:
        # Try fuzzy: check if stock name contains sector keywords
        for sname in SECTOR_MAP:
            if any(kw in stock_name for kw in ['银行','保险','证券','科技','医药','汽车','能源','钢铁','地产']):
                actual_sector = sname
                break

    # Now find this sector's performance in the sector ranking
    sector_name = actual_sector or '其他'
    sector_pct = 0.0
    sector_rank = 10
    sector_up_ratio = 0.5
    try:
        sectors_raw = api_sectors().get_json() if hasattr(api_sectors(), 'get_json') else {}
        # Also check concept sectors
        all_sectors = sectors_raw.get('industry', []) + sectors_raw.get('concept', [])
        for i, s in enumerate(all_sectors):
            if s.get('name') == actual_sector:
                sector_pct = s.get('pct', 0)
                sector_rank = i + 1
                sector_up_ratio = s.get('up_count', 10) / max(s.get('up_count', 10) + s.get('down_count', 10), 1) if 'up_count' in s else 0.5
                break
    except:
        pass

    try:
        result = generate_diagnosis(
            code=code,
            name=match.get('name', ''),
            klines=klines,
            market_state=market_state,
            sector_name=sector_name,
            sector_pct=sector_pct,
            sector_rank=sector_rank,
            sector_up_ratio=sector_up_ratio,
        )
        return jsonify(result)
    except Exception as e:
        print(f"Diagnosis error for {code}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnose/<code>/summary')
def api_diagnose_summary(code):
    """Free summary (1 paragraph) for unpaid users."""
    try:
        # Duplicate the diagnostic logic for standalone endpoint
        if EM_AVAILABLE:
            try:
                data = em_spot('all')
                stocks = [parse_spot(d) for d in data.get('data', {}).get('diff', [])] if data else []
            except:
                stocks = _gen_mock_stocks()
        else:
            stocks = _gen_mock_stocks()

        match = next((s for s in stocks if s['code'] == code), None)
        if not match:
            return jsonify({'error': f'Stock {code} not found'}), 404

        # Generate mock klines
        import random
        random.seed(hash(code) % 10000)
        base = match.get('pre_close', match.get('price', 50))
        klines = []
        for i in range(35, 0, -1):
            change = random.gauss(0, 0.025)
            base *= (1 + change)
            klines.append({
                'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'),
                'open': round(base * random.uniform(0.98, 1.02), 2),
                'close': round(base, 2),
                'high': round(base * random.uniform(1.0, 1.05), 2),
                'low': round(base * random.uniform(0.95, 1.0), 2),
                'volume': random.randint(500000, 20000000),
            })

        result = generate_diagnosis(
            code=code, name=match.get('name', ''),
            klines=klines, market_state='震荡偏多',
            sector_name='', sector_pct=0, sector_rank=10, sector_up_ratio=0.5,
        )

        structure = result.get('structure', '')
        score = result.get('observation_score', {})
        tags = [t['label'] for t in result.get('risk_tags', [])[:3]]
        stats = result.get('backtest', {})

        summary = (
            f"{result['meta']['name']}（{code}）当前量价结构为「{structure}」，"
            f"风险标签：{'、'.join(tags)}。"
            f"历史{stats.get('total_samples', 0)}次类似结构中，T+5胜率{stats.get('win_rate_t5', 0)}%，"
            f"综合观察优先级 {score.get('total', 0)}。"
        )

        return jsonify({
            'code': code,
            'name': result['meta']['name'],
            'structure': structure,
            'observation_score': score.get('total', 0),
            'risk_tags': tags,
            'win_rate_t5': stats.get('win_rate_t5', 0),
            'total_samples': stats.get('total_samples', 0),
            'summary': summary,
            'unlock_hint': '查看完整诊断报告（含历史相似结构详情、具体观察点、板块分析）',
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'data_source': 'eastmoney' if EM_AVAILABLE else 'mock',
        'time': datetime.now().isoformat(),
    })


@app.route('/api/backtest')
def api_backtest():
    try:
        with open('/opt/stock-app/backend/backtest_results.json', 'r') as f:
            return jsonify(json.load(f))
    except FileNotFoundError:
        return jsonify({'error': 'Backtest not yet run', 'status': 'pending'})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/scoring')
def api_scoring():
    try:
        with open('/opt/stock-app/backend/backtest_results.json', 'r') as f:
            bt = json.load(f)
    except:
        bt = None

    review_data = {}
    try:
        review_raw = json.loads(api_review().get_data(as_text=True))
        review_data = review_raw if isinstance(review_raw, dict) else {}
    except:
        pass

    market_state = review_data.get('sentiment', '震荡偏多')
    state_coeff = {'强势': 1.2, '偏强': 1.1, '震荡偏多': 1.0, '震荡偏空': 0.9, '偏弱': 0.7, '弱势': 0.5}
    ms_coeff = state_coeff.get(market_state, 1.0)

    stocks = _gen_mock_stocks()
    ranked = []
    for s in stocks[:50]:
        vol_r = s.get('volume_ratio', 1)
        pct = s.get('pct', 0)
        turnover = s.get('turnover', 0)
        factor_score = min(100, max(0, (pct + 10) * 3 + min(vol_r * 15, 30) + min(turnover / 3, 20)))
        bt_weight = 0.5
        if bt:
            for sd in bt.get('strategies', {}).values():
                if sd.get('overall_win_rate_t5', 0) > 50:
                    bt_weight = max(bt_weight, sd['overall_win_rate_t5'] / 100)
        composite = round(factor_score * bt_weight * ms_coeff, 1)
        ranked.append({
            'code': s['code'], 'name': s['name'], 'price': s['price'], 'pct': s['pct'],
            'volume_ratio': s['volume_ratio'], 'turnover': s['turnover'],
            'composite_score': composite, 'factor_score': round(factor_score, 1),
        })
    ranked.sort(key=lambda x: x['composite_score'], reverse=True)
    return jsonify({'market_state': market_state, 'state_coefficient': ms_coeff,
                    'backtest_available': bt is not None, 'ranked_stocks': ranked[:20]})


if __name__ == '__main__':
    # Pre-initialize the factor store to avoid first-request timeout
    from report_engine import get_matcher
    get_matcher()
    print("🚀 A股异动复盘助手 Backend")
    print("📍 http://localhost:5001")
    print("🔌 Data: Eastmoney API (primary) / Mock (fallback)")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
