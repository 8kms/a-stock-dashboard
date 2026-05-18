import React, { useState, useEffect, useCallback, useRef } from 'react'
import DiagnosisPanel from './DiagnosisPanel.jsx'

const API = '/api'
const COLORS = { up: '#e8393a', down: '#17c183', neutral: '#888' }

// ── Helpers ──
const fmt = (v, d = 2) => (typeof v === 'number' ? v.toFixed(d) : v)
const fmtB = (v) => {
  if (!v) return '—'
  const n = Number(v)
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万'
  return n.toFixed(0)
}
const fmtPct = (v) => {
  const s = Number(v) >= 0 ? '+' : ''
  return s + fmt(v)
}
const pctColor = (v) => Number(v) > 0 ? COLORS.up : Number(v) < 0 ? COLORS.down : COLORS.neutral

// ── Tag Component ──
const Tag = ({ label, type }) => {
  const colors = {
    danger: '#fff0f0',
    warning: '#fff8e8',
    info: '#e8f4ff',
  }
  const texts = {
    danger: '#e8393a',
    warning: '#e86a17',
    info: '#1677ff',
  }
  return (
    <span className="tag" style={{ background: colors[type] || colors.info, color: texts[type] || texts.info }}>
      {label}
    </span>
  )
}

// ── Market Bar ──
function MarketBar({ data, loading }) {
  const primaryIndices = ['sh_idx', 'sz_idx', 'cy_idx']
  const secondaryIndices = ['hs300_idx', 'zz500_idx', 'kc50_idx', 'sz50_idx']

  const renderIdx = (item) => (
    <span key={item.key} className="index-item">
      <span className="idx-name">{item.name}</span>
      <span className="idx-price">{loading ? '—' : (item.price || 0).toLocaleString()}</span>
    </span>
  )

  // Handle both old (dict) and new (list) API formats
  const idxList = Array.isArray(data) ? data : []
  const primaries = idxList.filter(d => primaryIndices.includes(d.key))
  const secondaries = idxList.filter(d => secondaryIndices.includes(d.key))

  return (
    <div className="market-bar">
      <div className="market-bar-inner">
        <span className="brand">📊 A股异动复盘助手</span>
        <div className="indices">
          {primaries.map(renderIdx)}
          <span className="idx-sep">|</span>
          {secondaries.map(renderIdx)}
        </div>
        <span className="update-time">实时数据</span>
      </div>
    </div>
  )
}

// ── Tab Bar ──
const TABS = [
  { key: 'diagnosis', label: '📋 个股诊断', icon: '' },
  { key: 'gainers', label: '🔥 涨幅榜', icon: '' },
  { key: 'sectors', label: '📂 板块榜', icon: '' },
  { key: 'volume', label: '📈 放量异动', icon: '' },
  { key: 'review', label: '📊 每日复盘', icon: '' },
  { key: 'strategies', label: '🎯 策略筛选', icon: '' },
  { key: 'watchlist', label: '⭐ 自选股', icon: '' },
]

// ── Stock Table ──
function StockTable({ data, loading, onSelect, columns, riskTags = true }) {
  if (loading) return <div className="loading-msg">加载中...</div>
  if (!data || data.length === 0) return <div className="loading-msg">暂无数据</div>

  return (
    <div className="stock-table-wrap">
      <table className="stock-table">
        <thead>
          <tr>
            {columns.map((c) => <th key={c.key} style={c.style || {}}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={row.code || i} onClick={() => onSelect && onSelect(row.code)} className="stock-row">
              {columns.map((c) => (
                <td key={c.key} style={c.style || {}}>
                  {c.render ? c.render(row, i) : (
                    <span style={{ color: c.pct ? pctColor(row[c.key]) : 'inherit' }}>
                      {fmt(row[c.key])}
                    </span>
                  )}
                </td>
              ))}
              {riskTags && (
                <td>
                  <div className="tags-row">
                    {(row.risk_tags || []).slice(0, 3).map((t, j) => (
                      <Tag key={j} label={t.label} type={t.type} />
                    ))}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Sector Cards ──
function SectorCards({ data, loading }) {
  if (loading) return <div className="loading-msg">加载板块数据...</div>
  const industry = data?.industry || []
  const concept = data?.concept || []

  return (
    <div>
      <h3 className="section-title">行业板块 Top 10</h3>
      <div className="sector-grid">
        {industry.slice(0, 10).map((s, i) => (
          <div key={i} className="sector-card">
            <div className="sector-name">{s.name}</div>
            <div className="sector-info">
              <span style={{ color: pctColor(s.pct), fontWeight: 700, fontSize: 16 }}>
                {fmtPct(s.pct)}%
              </span>
              <span className="sector-leader">领涨: {s.leader} {fmtPct(s.leader_pct)}%</span>
            </div>
            <div className="sector-count">
              <span className="up-count">上涨 {s.up_count || 0}</span>
              <span className="down-count">下跌 {s.down_count || 0}</span>
            </div>
          </div>
        ))}
      </div>
      <h3 className="section-title" style={{ marginTop: 20 }}>概念板块 Top 10</h3>
      <div className="sector-grid">
        {concept.slice(0, 10).map((s, i) => (
          <div key={i} className="sector-card concept-card">
            <div className="sector-name">{s.name}</div>
            <div className="sector-info">
              <span style={{ color: pctColor(s.pct), fontWeight: 700, fontSize: 16 }}>
                {fmtPct(s.pct)}%
              </span>
              <span className="sector-leader">领涨: {s.leader} {fmtPct(s.leader_pct)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Daily Review ──
function DailyReview({ data, loading }) {
  if (loading) return <div className="loading-msg">生成每日复盘...</div>
  if (!data || data.error) return <div className="loading-msg">复盘数据生成中，请稍后刷新</div>

  const mb = data.market_breadth || {}
  const totalTips = [
    '今日最强板块：' + (data.top_sectors || []).map(s => `${s.name}(${fmtPct(s.pct)}%)`).join('、'),
    `涨停${mb.limit_up}家 | 跌停${mb.limit_down}家 | 涨跌比 ${mb.ratio || '—'}`,
    '市场情绪：' + data.sentiment + ' — ' + data.sentiment_desc,
  ]

  return (
    <div className="review-panel">
      <div className="review-date">📅 {data.date} 每日复盘</div>
      <div className="review-summary">{data.summary}</div>

      <div className="review-grid">
        <div className="review-card">
          <h4>📊 市场广度</h4>
          <div className="breadth-bars">
            <div className="breadth-row">
              <span>上涨</span>
              <div className="bar-wrap"><div className="bar up-bar" style={{ width: `${Math.min(mb.up / Math.max(mb.up + mb.down, 1) * 100, 100)}%` }}>{mb.up}</div></div>
            </div>
            <div className="breadth-row">
              <span>下跌</span>
              <div className="bar-wrap"><div className="bar down-bar" style={{ width: `${Math.min(mb.down / Math.max(mb.up + mb.down, 1) * 100, 100)}%` }}>{mb.down}</div></div>
            </div>
          </div>
        </div>

        <div className="review-card">
          <h4>⚠️ 高风险个股</h4>
          {data.risk_stocks?.slice(0, 8).map((s, i) => (
            <div key={i} className="risk-row">
              <span className="risk-name">{s.name}</span>
              <span style={{ color: pctColor(s.pct), fontWeight: 700 }}>{fmtPct(s.pct)}%</span>
              <span className="risk-tags">{s.tags?.join(' · ')}</span>
            </div>
          ))}
        </div>

        <div className="review-card">
          <h4>📈 放量异动</h4>
          {data.volume_anomaly?.slice(0, 8).map((v, i) => (
            <div key={i} className="risk-row">
              <span className="risk-name">{v.name}</span>
              <span style={{ color: pctColor(v.pct), fontWeight: 700 }}>{fmtPct(v.pct)}%</span>
              <span className="risk-tags">量比 {fmt(v.volume_ratio, 1)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="review-tips">
        {totalTips.map((t, i) => <div key={i} className="tip-item">{t}</div>)}
      </div>
    </div>
  )
}

// ── Strategy Filter ──
const STRATEGY_TEMPLATES = [
  { key: 'low_volume_breakout', name: '低位放量', desc: '涨幅2-7% + 量比>1.5' },
  { key: 'sector_leader', name: '板块龙头', desc: '涨幅>5% + 换手>5%' },
  { key: 'high_dividend', name: '高股息/低PE', desc: 'PE<15 + 上涨' },
  { key: 'pullback_stable', name: '回调企稳', desc: '小涨0.5-3% + 量比~1' },
  { key: 'strong_breakout', name: '强势突破', desc: '涨幅>7%' },
  { key: 'shrink_then_expand', name: '缩量后放量', desc: '量比>2 + 上涨' },
]

function StrategyPanel() {
  const [strategy, setStrategy] = useState('low_volume_breakout')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [backtestData, setBacktestData] = useState(null)

  const fetchData = useCallback(async (st) => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/strategies?type=${st}`)
      const json = await res.json()
      setData(json)
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData(strategy) }, [strategy])

  // Fetch backtest data for win rate display
  useEffect(() => {
    fetch('/api/backtest').then(r => r.json()).then(d => {
      if (!d.error) setBacktestData(d.strategies)
    }).catch(() => {})
  }, [])

  const cols = [
    { key: 'code', label: '代码' },
    { key: 'name', label: '名称' },
    { key: 'price', label: '最新价' },
    { key: 'pct', label: '涨跌幅', pct: true },
    { key: 'volume_ratio', label: '量比' },
    { key: 'turnover', label: '换手率' },
    { key: 'pe', label: '市盈率' },
  ].map(c => ({ ...c, render: c.pct
    ? (r) => <span style={{ color: pctColor(r.pct), fontWeight: 600 }}>{fmtPct(r.pct)}%</span>
    : c.key === 'volume_ratio' ? (r) => <span style={{ color: r.volume_ratio > 2 ? COLORS.up : '' }}>{fmt(r.volume_ratio, 2)}</span>
    : c.key === 'turnover' ? (r) => <span style={{ color: r.turnover > 10 ? COLORS.up : '' }}>{fmt(r.turnover, 2)}%</span>
    : c.key === 'price' ? (r) => fmt(r.price)
    : undefined,
  }))

  const btForStrategy = backtestData?.[strategy]
  const currentBt = btForStrategy || {}

  return (
    <div>
      <div className="strategy-tabs">
        {STRATEGY_TEMPLATES.map((s) => {
          const bt = backtestData?.[s.key]
          const wr = bt?.overall_win_rate_t5
          return (
            <button
              key={s.key}
              className={`strategy-btn ${strategy === s.key ? 'active' : ''}`}
              onClick={() => setStrategy(s.key)}
              title={s.desc}
            >
              {s.name}
              {wr != null && <span className="strategy-wr" style={{color: wr>=50?'#34d399':wr>=40?'#fbbf24':'#f87171'}}> {wr}%</span>}
            </button>
          )
        })}
      </div>
      <p className="strategy-desc">
        {STRATEGY_TEMPLATES.find(s => s.key === strategy)?.desc} — 共 {data.length} 只
      </p>
      {btForStrategy && currentBt.total_signals > 0 && (
        <div className="bt-stats-bar">
          <span>📊 历史回测: <strong>{currentBt.total_signals}</strong> 次信号</span>
          <span>T+5胜率: <strong style={{color:currentBt.overall_win_rate_t5>=50?'#34d399':'#fbbf24'}}>{currentBt.overall_win_rate_t5}%</strong></span>
          <span>平均收益: <strong style={{color:currentBt.overall_avg_ret_t5>0?'#e8393a':'#17c183'}}>{currentBt.overall_avg_ret_t5>0?'+':''}{currentBt.overall_avg_ret_t5}%</strong></span>
          {currentBt.by_state && (
            <div className="bt-state-grid">
              {Object.entries(currentBt.by_state).map(([state, d]) => (
                <span key={state} className="bt-state-item" title={`${state}市场: ${d.signals}次信号, T+5胜率${d.win_rate_t5}%`}>
                  {state}: {d.win_rate_t5}%
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <StockTable data={data} loading={loading} columns={cols} riskTags={false} />
    </div>
  )
}

// ── Watchlist ──
function WatchlistPanel() {
  const [stocks, setStocks] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('watchlist') || '[]')
    } catch { return [] }
  })
  const [input, setInput] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [watchData, setWatchData] = useState([])
  const [loading, setLoading] = useState(false)
  const [showSearch, setShowSearch] = useState(false)

  const save = (list) => {
    setStocks(list)
    localStorage.setItem('watchlist', JSON.stringify(list))
  }

  const doSearch = async (q) => {
    setInput(q)
    if (q.length < 1) { setSearchResults([]); setShowSearch(false); return }
    setShowSearch(true)
    try {
      const res = await fetch(`${API}/search?q=${encodeURIComponent(q)}`)
      const json = await res.json()
      setSearchResults(json)
    } catch (e) { console.error(e) }
  }

  const addStock = (s) => {
    if (stocks.find(x => x.code === s.code)) return
    save([...stocks, { code: s.code, name: s.name }])
    setInput('')
    setShowSearch(false)
  }

  const removeStock = (code) => save(stocks.filter(s => s.code !== code))

  const fetchWatchData = useCallback(async () => {
    if (stocks.length === 0) { setWatchData([]); return }
    setLoading(true)
    try {
      const results = await Promise.all(
        stocks.map(async (s) => {
          try {
            const res = await fetch(`${API}/stock/${s.code}`)
            return await res.json()
          } catch { return { code: s.code, name: s.name, price: 0, pct: 0 } }
        })
      )
      setWatchData(results)
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [stocks])

  useEffect(() => { fetchWatchData(); const t = setInterval(fetchWatchData, 10000); return () => clearInterval(t) }, [fetchWatchData])

  const cols = [
    { key: 'code', label: '代码' },
    { key: 'name', label: '名称' },
    { key: 'price', label: '最新价', render: (r) => fmt(r.price) },
    { key: 'pct', label: '涨跌幅', pct: true, render: (r) => <span style={{ color: pctColor(r.pct), fontWeight: 600 }}>{fmtPct(r.pct)}%</span> },
    { key: 'volume_ratio', label: '量比', render: (r) => <span style={{ color: (r.volume_ratio || 0) > 2 ? COLORS.up : '' }}>{fmt(r.volume_ratio, 2)}</span> },
    { key: 'turnover', label: '换手率', render: (r) => <span style={{ color: (r.turnover || 0) > 10 ? COLORS.up : '' }}>{fmt(r.turnover, 2)}%</span> },
    { key: 'action', label: '操作', render: (r) => <button className="btn-sm btn-danger" onClick={(e) => { e.stopPropagation(); removeStock(r.code) }}>删除</button> },
  ]

  return (
    <div>
      <div className="watchlist-add">
        <div className="search-wrap">
          <input
            className="search-input"
            placeholder="搜索股票代码或名称..."
            value={input}
            onChange={(e) => doSearch(e.target.value)}
            onFocus={() => stocks.length > 0 && setShowSearch(true)}
          />
          {showSearch && searchResults.length > 0 && (
            <div className="search-dropdown">
              {searchResults.map((s) => (
                <div key={s.code} className="search-item" onClick={() => addStock(s)}>
                  <span>{s.code}</span>
                  <span>{s.name}</span>
                  <span style={{ color: pctColor(s.pct) }}>{fmtPct(s.pct)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <StockTable data={watchData} loading={loading} columns={cols} riskTags={true} />
    </div>
  )
}

// ── Stock Detail Modal ──
function StockDetail({ code, onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!code) return
    setLoading(true)
    fetch(`${API}/stock/${code}`)
      .then(r => r.json())
      .then(d => { setDetail(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [code])

  if (!code) return null
  if (loading) return <div className="modal-overlay" onClick={onClose}><div className="modal-box"><div className="loading-msg">加载中...</div></div></div>

  const d = detail || {}
  const isUp = Number(d.pct) >= 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-name">{d.name}</span>
            <span className="modal-code">{d.code}</span>
          </div>
          <button className="btn-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-price-row">
          <span className="modal-price" style={{ color: isUp ? COLORS.up : COLORS.down }}>
            {fmt(d.price)}
          </span>
          <span className="modal-pct" style={{ background: isUp ? COLORS.up : COLORS.down }}>
            {fmtPct(d.pct)}%
          </span>
        </div>
        <div className="modal-grid">
          {[['开盘', d.open], ['最高', d.high], ['最低', d.low], ['昨收', d.pre_close],
            ['成交额', fmtB(d.amount)], ['换手率', fmt(d.turnover) + '%'],
            ['量比', fmt(d.volume_ratio, 2)], ['市盈率', fmt(d.pe)]].map(([l, v]) => (
            <div key={l} className="modal-cell">
              <div className="modal-cell-label">{l}</div>
              <div className="modal-cell-value">{v}</div>
            </div>
          ))}
        </div>
        <div className="modal-tags">
          {(d.risk_tags || []).map((t, i) => <Tag key={i} label={t.label} type={t.type} />)}
        </div>
        {d.sector && <div className="modal-sector">所属板块: {d.sector}</div>}
      </div>
    </div>
  )
}

// ═══════════════════════════════════
//  MAIN APP
// ═══════════════════════════════════
export default function App() {
  const [activeTab, setActiveTab] = useState('diagnosis')
  const [marketData, setMarketData] = useState([])
  const [marketLoading, setMarketLoading] = useState(true)
  const [gainers, setGainers] = useState([])
  const [gainersLoading, setGainersLoading] = useState(true)
  const [sectors, setSectors] = useState({ industry: [], concept: [] })
  const [sectorsLoading, setSectorsLoading] = useState(true)
  const [volume, setVolume] = useState([])
  const [volumeLoading, setVolumeLoading] = useState(true)
  const [review, setReview] = useState(null)
  const [reviewLoading, setReviewLoading] = useState(true)
  const [selectedStock, setSelectedStock] = useState(null)
  const pollingRef = useRef(null)

  const fetchAll = useCallback(async () => {
    try {
      const [mRes, gRes, sRes, vRes, rRes] = await Promise.all([
        fetch(`${API}/market`).then(r => r.json()),
        fetch(`${API}/gainers`).then(r => r.json()),
        fetch(`${API}/sectors`).then(r => r.json()),
        fetch(`${API}/volume`).then(r => r.json()),
        fetch(`${API}/review`).then(r => r.json()),
      ])
      setMarketData(mRes); setMarketLoading(false)
      setGainers(gRes); setGainersLoading(false)
      setSectors(sRes); setSectorsLoading(false)
      setVolume(vRes); setVolumeLoading(false)
      setReview(rRes); setReviewLoading(false)
    } catch (e) { console.error('Fetch error:', e) }
  }, [])

  useEffect(() => {
    fetchAll()
    pollingRef.current = setInterval(fetchAll, 10000)
    return () => clearInterval(pollingRef.current)
  }, [fetchAll])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') setSelectedStock(null)
      if (e.ctrlKey || e.metaKey) {
        const idx = TABS.findIndex(t => t.key === activeTab)
        if (e.key === 'ArrowRight') { e.preventDefault(); setActiveTab(TABS[Math.min(idx + 1, TABS.length - 1)].key) }
        if (e.key === 'ArrowLeft') { e.preventDefault(); setActiveTab(TABS[Math.max(idx - 1, 0)].key) }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [activeTab])

  const gainerCols = [
    { key: 'code', label: '代码', style: { width: 90 } },
    { key: 'name', label: '名称', style: { width: 90 } },
    { key: 'price', label: '最新价', style: { width: 80 }, render: (r) => fmt(r.price) },
    { key: 'pct', label: '涨跌幅', style: { width: 90 }, pct: true,
      render: (r) => <span style={{ color: pctColor(r.pct), fontWeight: 700, fontSize: 14 }}>{fmtPct(r.pct)}%</span> },
    { key: 'volume_ratio', label: '量比', style: { width: 65 },
      render: (r) => <span style={{ color: r.volume_ratio > 2 ? '#e86a17' : '' }}>{fmt(r.volume_ratio, 2)}</span> },
    { key: 'turnover', label: '换手率', style: { width: 80 },
      render: (r) => <span style={{ color: r.turnover > 15 ? '#e8393a' : r.turnover > 10 ? '#e86a17' : '' }}>{fmt(r.turnover, 2)}%</span> },
    { key: 'amount', label: '成交额', style: { width: 90 }, render: (r) => fmtB(r.amount) },
    { key: 'pe', label: 'PE', style: { width: 70 },
      render: (r) => r.pe > 0 ? fmt(r.pe, 1) : <span style={{ color: '#888' }}>亏损</span> },
  ]

  const volumeCols = [
    { key: 'code', label: '代码', style: { width: 90 } },
    { key: 'name', label: '名称', style: { width: 90 } },
    { key: 'price', label: '最新价', style: { width: 80 }, render: (r) => fmt(r.price) },
    { key: 'pct', label: '涨跌幅', style: { width: 90 },
      render: (r) => <span style={{ color: pctColor(r.pct), fontWeight: 700 }}>{fmtPct(r.pct)}%</span> },
    { key: 'volume_ratio', label: '量比', style: { width: 80 },
      render: (r) => <span style={{ color: '#e86a17', fontWeight: 700 }}>{fmt(r.volume_ratio, 2)}</span> },
    { key: 'turnover', label: '换手率', style: { width: 80 },
      render: (r) => <span style={{ color: r.turnover > 15 ? '#e8393a' : '' }}>{fmt(r.turnover, 2)}%</span> },
    { key: 'amount', label: '成交额', style: { width: 90 }, render: (r) => fmtB(r.amount) },
  ]

  return (
    <div className="app">
      <MarketBar data={marketData} loading={marketLoading} />

      <div className="main-container">
        <div className="tab-bar">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="content-area">
          {activeTab === 'diagnosis' && (
            <DiagnosisPanel />
          )}
          {activeTab === 'gainers' && (
            <StockTable data={gainers} loading={gainersLoading} columns={gainerCols} onSelect={setSelectedStock} riskTags={true} />
          )}
          {activeTab === 'sectors' && (
            <SectorCards data={sectors} loading={sectorsLoading} />
          )}
          {activeTab === 'volume' && (
            <StockTable data={volume} loading={volumeLoading} columns={volumeCols} onSelect={setSelectedStock} riskTags={true} />
          )}
          {activeTab === 'review' && (
            <DailyReview data={review} loading={reviewLoading} />
          )}
          {activeTab === 'strategies' && (
            <StrategyPanel />
          )}
          {activeTab === 'watchlist' && (
            <WatchlistPanel />
          )}
        </div>
      </div>

      {selectedStock && (
        <StockDetail code={selectedStock} onClose={() => setSelectedStock(null)} />
      )}
    </div>
  )
}
