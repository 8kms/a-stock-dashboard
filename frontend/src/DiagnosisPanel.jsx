import React, { useState, useCallback } from 'react'

const API = '/api'

function Tag({ label, type }) {
  const c = { danger: '#fff0f0', warning: '#fff8e8', info: '#e8f4ff' }
  const t = { danger: '#e8393a', warning: '#e86a17', info: '#1677ff' }
  return <span className="tag" style={{ background: c[type] || c.info, color: t[type] || t.info }}>{label}</span>
}

const fmtPct = v => { const n = Number(v); return (n >= 0 ? '+' : '') + (typeof v === 'number' ? v.toFixed(2) : v) + '%' }
const pctColor = v => Number(v) > 0 ? '#e8393a' : Number(v) < 0 ? '#17c183' : '#888'
const fmtVol = v => { if (!v) return '—'; const n = Number(v); return n >= 1e8 ? (n / 1e8).toFixed(2) + '亿' : (n / 1e4).toFixed(1) + '万' }

export default function DiagnosisPanel() {
  const [code, setCode] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [loading, setLoading] = useState(false)
  const [stage, setStage] = useState('')
  const [summary, setSummary] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')

  const doSearch = useCallback(async (q) => {
    setCode(q)
    if (q.length < 1) { setSearchResults([]); setShowDropdown(false); return }
    try {
      const r = await fetch(`${API}/search?q=${encodeURIComponent(q)}`)
      const d = await r.json()
      if (Array.isArray(d) && d.length > 0) { setSearchResults(d.slice(0, 8)); setShowDropdown(true) }
      else { setSearchResults([]); setShowDropdown(false) }
    } catch { setSearchResults([]) }
  }, [])

  const runDiagnosis = useCallback(async (input) => {
    setShowDropdown(false); setLoading(true); setError(''); setSummary(null); setReport(null)
    setStage('正在获取实时行情...')

    let stockCode = input
    if (!/^\d{6}$/.test(input)) {
      try {
        const sr = await fetch(`${API}/search?q=${encodeURIComponent(input)}`)
        const d = await sr.json()
        if (Array.isArray(d) && d.length > 0) stockCode = d[0].code
        else { setError(`未找到「${input}」，请直接输入6位股票代码`); setLoading(false); return }
      } catch { setError('搜索失败'); setLoading(false); return }
    }

    setStage('正在计算量价因子...')
    try {
      const sr = await fetch(`${API}/diagnose/${stockCode}/summary`)
      const sd = await sr.json()
      if (sd.error) { setError(sd.error); setLoading(false); return }
      setSummary(sd)
      setStage('正在匹配历史相似结构...')

      const fr = await fetch(`${API}/diagnose/${stockCode}`)
      const fd = await fr.json()
      if (fd.error) { setError(fd.error) }
      else { setReport(fd); setStage('') }
    } catch { setError('网络错误，请重试') }
    setLoading(false)
  }, [])

  const selectStock = (s) => { setCode(s.code); runDiagnosis(s.code) }
  const handleSubmit = (e) => { e.preventDefault(); runDiagnosis(code.trim()) }

  const structColors = {
    '放量突破': '#34d399', '缩量上涨': '#60a5fa', '缩量回踩': '#fbbf24',
    '放量下跌': '#f87171', '高位长上影分歧': '#f87171', '高位放量滞涨': '#f87171',
    '低位放量企稳': '#34d399', '低位缩量筑底': '#60a5fa', '震荡整理': '#8b949e',
  }

  // ── Render helpers ──
  const r = report
  const stats = r?.backtest || {}
  const score = r?.observation_score || {}
  const ctx = r?.market_context || {}
  const judg = r?.comprehensive_judgment || {}

  return (
    <div className="diagnosis-panel">
      {/* Search */}
      <form onSubmit={handleSubmit} className="diag-search-form">
        <div className="diag-search-wrap">
          <input className="diag-search-input" type="text" placeholder="输入股票代码或名称，如 贵州茅台 / 600519..."
            value={code} onChange={(e) => doSearch(e.target.value)}
            onFocus={() => searchResults.length > 0 && setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 200)} autoFocus />
          {showDropdown && searchResults.length > 0 && (
            <div className="diag-search-dropdown">
              {searchResults.map((s) => (
                <div key={s.code} className="diag-search-item" onMouseDown={() => selectStock(s)}>
                  <span className="diag-search-item-code">{s.code}</span>
                  <span className="diag-search-item-name">{s.name}</span>
                  <span style={{ color: pctColor(s.pct), fontWeight: 600 }}>{fmtPct(s.pct)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <button type="submit" className="diag-search-btn" disabled={loading}>🔍 生成诊断报告</button>
      </form>

      {error && <div className="diag-error">{error}</div>}

      {/* Loading with stage */}
      {loading && (
        <div className="diag-loading">
          <div className="diag-loading-card">
            <div className="diag-spinner" />
            <div className="diag-loading-stage">{stage}</div>
            <div className="diag-loading-sub">预计耗时 2-8 秒，请稍候...</div>
          </div>
        </div>
      )}

      {/* Summary */}
      {summary && !loading && (
        <div className="diag-summary-box">
          <div className="diag-summary-header">
            <span className="diag-stock-name">{summary.name}</span>
            <span className="diag-stock-code">{summary.code}</span>
            {summary.structure && (
              <span className="diag-structure-badge" style={{
                background: (structColors[summary.structure] || '#8b949e') + '22',
                color: structColors[summary.structure] || '#8b949e',
                border: '1px solid ' + (structColors[summary.structure] || '#8b949e') + '44',
              }}>{summary.structure}</span>
            )}
          </div>
          <div className="diag-summary-text">{summary.summary}</div>
          <div className="diag-summary-tags">
            {(summary.risk_tags || []).map((t, i) => <Tag key={i} label={t}
              type={t.includes('追高') || t.includes('长上影') || t.includes('涨停') ? 'danger' : 'warning'} />)}
          </div>
        </div>
      )}

      {/* Full Report */}
      {r && !loading && (
        <div className="diag-full-report">

          {/* ── 1. Structure ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">1</span> 量价结构与 K 线走势</div>
            <div className="diag-structure-desc">{r.structure_analysis}</div>

            {/* K-line table */}
            <div className="diag-kline-wrap">
              <table className="diag-table diag-kline-table">
                <thead><tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>涨跌</th><th>振幅</th><th>成交量</th></tr></thead>
                <tbody>
                  {(r.kline_table || []).map((k, i) => (
                    <tr key={i} className={i === (r.kline_table || []).length - 1 ? 'kline-today' : ''}>
                      <td>{i === (r.kline_table || []).length - 1 ? <strong>{k.date}</strong> : k.date}</td>
                      <td>{k.open}</td>
                      <td style={{ color: '#f87171' }}>{k.high}</td>
                      <td style={{ color: '#17c183' }}>{k.low}</td>
                      <td style={{ fontWeight: 600, color: k.change >= 0 ? '#f87171' : '#17c183' }}>{k.close}</td>
                      <td style={{ color: pctColor(k.change) }}>{fmtPct(k.change)}</td>
                      <td>{k.amplitude}%</td>
                      <td>{fmtVol(k.volume)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── 2. Backtest ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">2</span> 历史相似结构统计</div>
            {stats.total_samples > 0 ? (<>
              <div className="diag-card-row">
                <div className="diag-stat-card"><div className="diag-stat-label">历史相似样本</div><div className="diag-stat-value" style={{ color: '#58a6ff' }}>{stats.total_samples}<span style={{ fontSize: 14 }}>次</span></div></div>
                <div className="diag-stat-card"><div className="diag-stat-label">T+1 胜率</div><div className="diag-stat-value" style={{ color: stats.win_rate_t1 > 50 ? '#34d399' : '#f87171', fontSize: 18 }}>{stats.win_rate_t1}%</div></div>
                <div className="diag-stat-card"><div className="diag-stat-label">T+5 胜率</div><div className="diag-stat-value" style={{ color: stats.win_rate_t5 > 50 ? '#34d399' : '#f87171', fontSize: 22 }}>{stats.win_rate_t5}%</div></div>
                <div className="diag-stat-card"><div className="diag-stat-label">T+10 胜率</div><div className="diag-stat-value" style={{ color: stats.win_rate_t10 > 50 ? '#34d399' : '#f87171', fontSize: 18 }}>{stats.win_rate_t10}%</div></div>
              </div>
              <table className="diag-table">
                <thead><tr><th>时间窗口</th><th>胜率</th><th>平均收益</th><th>5日最大回撤中位数</th></tr></thead>
                <tbody>
                  <tr><td>T+1</td><td>{stats.win_rate_t1}%</td><td style={{ color: pctColor(stats.avg_ret_t1) }}>{fmtPct(stats.avg_ret_t1)}</td><td>—</td></tr>
                  <tr><td>T+3</td><td>{stats.win_rate_t3}%</td><td style={{ color: pctColor(stats.avg_ret_t3) }}>{fmtPct(stats.avg_ret_t3)}</td><td>—</td></tr>
                  <tr style={{ background: '#1a2332' }}><td><strong>T+5</strong></td><td><strong>{stats.win_rate_t5}%</strong></td><td style={{ color: pctColor(stats.avg_ret_t5), fontWeight: 700 }}>{fmtPct(stats.avg_ret_t5)}</td><td style={{ color: '#f87171' }}>{stats.median_max_dd_5}%</td></tr>
                  <tr><td>T+10</td><td>{stats.win_rate_t10}%</td><td style={{ color: pctColor(stats.avg_ret_t10) }}>{fmtPct(stats.avg_ret_t10)}</td><td>—</td></tr>
                </tbody>
              </table>

              {/* Market-state stratified */}
              {stats.by_market_state && Object.keys(stats.by_market_state).length > 0 && (
                <>
                  <div className="diag-subtitle">分市场状态统计</div>
                  <table className="diag-table">
                    <thead><tr><th>市场状态</th><th>样本数</th><th>T+5 胜率</th><th>T+5 平均收益</th></tr></thead>
                    <tbody>
                      {Object.entries(stats.by_market_state).map(([state, data]) => (
                        <tr key={state} className={state.includes(ctx.state?.slice(0, 2) || '') ? 'kline-today' : ''}>
                          <td>{state}{state.includes(ctx.state?.slice(0, 2) || '') ? <span style={{ color: '#fbbf24', fontSize: 11, marginLeft: 6 }}>← 当前</span> : ''}</td>
                          <td>{data.samples}</td>
                          <td style={{ color: data.win_rate_t5 > 50 ? '#34d399' : '#f87171', fontWeight: 600 }}>{data.win_rate_t5}%</td>
                          <td style={{ color: pctColor(data.avg_ret_t5) }}>{fmtPct(data.avg_ret_t5)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </>) : (
              <div className="diag-no-match">ℹ️ 历史数据库中未找到足够相似样本，建议关注基础风险标签。</div>
            )}
          </div>

          {/* ── 3. Sector ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">3</span> 板块环境</div>
            <div className="diag-card-row">
              <div className="diag-stat-card"><div className="diag-stat-label">{ctx.sector_name || '所属'}板块</div><div className="diag-stat-value" style={{ color: ctx.sector_pct > 0 ? '#e8393a' : '#17c183', fontSize: 20 }}>{ctx.sector_pct > 0 ? '+' : ''}{ctx.sector_pct}%</div></div>
              <div className="diag-stat-card"><div className="diag-stat-label">行业排名</div><div className="diag-stat-value" style={{ color: ctx.sector_rank <= 3 ? '#34d399' : ctx.sector_rank <= 10 ? '#fbbf24' : '#8b949e', fontSize: 20 }}>#{ctx.sector_rank}</div></div>
              <div className="diag-stat-card"><div className="diag-stat-label">板块上涨比例</div><div className="diag-stat-value" style={{ fontSize: 20 }}>{(ctx.sector_up_ratio * 100).toFixed(0)}%</div></div>
              <div className="diag-stat-card"><div className="diag-stat-label">市场情绪</div><div className="diag-stat-value" style={{ fontSize: 18, color: ctx.state?.includes('强') ? '#34d399' : ctx.state?.includes('弱') ? '#f87171' : '#fbbf24' }}>{ctx.state}</div></div>
            </div>
            <div className="diag-sector-analysis">{r.sector_analysis}</div>
          </div>

          {/* ── 4. Risk Tags ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">4</span> 风险标签</div>
            <div className="diag-tags-row">{(r.risk_tags || []).map((t, i) => <Tag key={i} label={t.label} type={t.type} />)}</div>
          </div>

          {/* ── 5. Observation Points ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">5</span> 持有者观察点</div>
            <p className="diag-note">以下不是买卖建议，而是如果持有该股，后续需要重点跟踪的信号——</p>
            {(r.observation_points || []).map((pt, i) => (
              <div key={i} className="diag-observe-item">
                <div className="diag-observe-cond">{pt.icon} {pt.condition}</div>
                <div className="diag-observe-detail">{pt.detail}</div>
              </div>
            ))}
          </div>

          {/* ── 6. Score + Judgment ── */}
          <div className="diag-section">
            <div className="diag-section-title"><span className="diag-sec-num">6</span> 综合评分</div>

            <div className="diag-score-box">
              <div className="diag-score-formula">观察优先级 = (市场环境×0.30) + (板块强度×0.25) + (量价信号×0.35) − 风险扣分×胜率加权</div>
              {score.breakdown && (
                <div className="diag-score-detail">
                  市场: {score.breakdown.market_env} + 板块: {score.breakdown.sector_strength} + 信号: {score.breakdown.signal_quality} − 风险: {Math.abs(score.breakdown.risk_penalty).toFixed(3)}
                </div>
              )}
              <div className="diag-score-row">
                <span className="diag-score-value" style={{ color: score.total < 0 ? '#f87171' : score.total < 0.3 ? '#fbbf24' : score.total < 0.5 ? '#60a5fa' : '#34d399' }}>{score.total}</span>
                <span className="diag-score-label">/ 1.0 — {score.interpretation}</span>
              </div>
              <div className="diag-score-bar"><div className="diag-score-fill" style={{ width: `${Math.max(0, Math.min(100, score.total * 100))}%`, background: score.total < 0 ? '#f87171' : score.total < 0.3 ? '#fbbf24' : score.total < 0.5 ? '#60a5fa' : '#34d399' }} /></div>
            </div>

            {/* Data notice */}
            {judg.data_notice && (
              <div className="diag-data-notice">{judg.data_notice}</div>
            )}

            {/* Comprehensive judgment */}
            <div className="diag-judgment" style={{ borderLeftColor: judg.risk_color }}>
              <div className="diag-judgment-header">综合判断 — 风险等级: <span style={{ color: judg.risk_color, fontWeight: 700 }}>{judg.risk_level}</span></div>
              <div className="diag-judgment-text">{judg.summary}</div>
            </div>

            {/* Grade stars */}
            <div className="diag-grades">
              <div className="diag-grade-row"><span className="diag-grade-l">量价结构质量</span>{Array.from({length:5},(_,i)=><span key={i} className={i < judg.structure_quality ? 'star' : 'star-off'}>★</span>)}</div>
              <div className="diag-grade-row"><span className="diag-grade-l">板块环境</span>{Array.from({length:5},(_,i)=><span key={i} className={i < judg.sector_quality ? 'star' : 'star-off'}>★</span>)}</div>
              <div className="diag-grade-row"><span className="diag-grade-l">市场环境</span>{Array.from({length:5},(_,i)=><span key={i} className={i < judg.market_quality ? 'star' : 'star-off'}>★</span>)}</div>
            </div>
          </div>

          {/* ── 7. Top Matches ── */}
          {r.top_matches?.length > 0 && (
            <div className="diag-section">
              <div className="diag-section-title"><span className="diag-sec-num">7</span> 最相似历史样本</div>
              <div className="diag-kline-wrap">
                <table className="diag-table"><thead><tr><th>日期</th><th>结构</th><th>相似度</th><th>T+5 收益</th><th>5日最大回撤</th></tr></thead>
                  <tbody>{(r.top_matches || []).slice(0, 8).map((m, i) => (
                    <tr key={i}><td>{m.date}</td><td>{m.structure}</td><td>{(m.similarity * 100).toFixed(1)}%</td>
                      <td style={{ color: pctColor(m.ret_t5), fontWeight: 600 }}>{fmtPct(m.ret_t5)}</td>
                      <td style={{ color: '#f87171' }}>{m.max_dd_5}%</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── 8. Factors (collapse) ── */}
          <details className="diag-details">
            <summary className="diag-details-summary">📊 因子详情与分位数</summary>
            <table className="diag-table diag-table-sm"><thead><tr><th>因子</th><th>当前值</th><th>同类分位</th><th>因子</th><th>当前值</th><th>同类分位</th></tr></thead>
              <tbody>
                {(() => {
                  const fp = r.factor_percentiles || {}
                  const entries = Object.entries(fp)
                  const rows = []
                  for (let i = 0; i < entries.length; i += 2) {
                    const [k1, v1] = entries[i]
                    const [k2, v2] = entries[i + 1] || ['', {}]
                    rows.push(<tr key={i}>
                      <td style={{ color: '#8b949e', fontSize: 12 }}>{k1}</td><td>{v1.value}</td>
                      <td><span className="diag-pct-bar"><span className="diag-pct-fill" style={{ width: `${v1.percentile || 50}%` }} /></span>{v1.percentile || 50}%</td>
                      <td style={{ color: '#8b949e', fontSize: 12 }}>{k2}</td><td>{v2.value || ''}</td>
                      <td>{v2.percentile ? <><span className="diag-pct-bar"><span className="diag-pct-fill" style={{ width: `${v2.percentile}%` }} /></span>{v2.percentile}%</> : ''}</td>
                    </tr>)
                  }
                  return rows
                })()}
              </tbody>
            </table>
            <div className="diag-meta">
              报告生成: {r.meta?.report_time} · 耗时 {r.meta?.generation_ms}ms ·
              <strong>免责声明</strong>: 本报告仅基于公开量价数据进行结构化分析，不构成投资建议。历史统计不代表未来表现。
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
