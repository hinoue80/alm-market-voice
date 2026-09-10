import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

const WEIGHT_STARS = (w) => '★'.repeat(Math.round(w)) + '☆'.repeat(5 - Math.round(w));

const SOURCE_TYPE_LABELS = {
  practitioner_community: 'Community',
  practitioner_pub:       'Practitioner Pub',
  conference:             'Conference',
  trade_media:            'Trade Media',
  rss:                    'Analyst',
};

function MomentumBar({ value, max }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        height: 6, width: 80, background: '#e0e0e0', borderRadius: 3, overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: pct > 60 ? '#0f62fe' : pct > 30 ? '#8a3ffc' : '#6f6f6f',
          borderRadius: 3,
          transition: 'width 0.3s',
        }} />
      </div>
      <span style={{ fontSize: 11, color: '#525252', fontVariantNumeric: 'tabular-nums' }}>
        {value.toFixed(1)}
      </span>
    </div>
  );
}

function EvidenceBadge({ weight }) {
  const w = Math.round(weight || 0);
  const color = w >= 4 ? '#198038' : w >= 2 ? '#0f62fe' : '#8d8d8d';
  return (
    <span style={{ color, fontSize: 13, letterSpacing: 1, fontVariantNumeric: 'tabular-nums' }}
      title={`Evidence weight: ${w}/5`}>
      {WEIGHT_STARS(w)}
    </span>
  );
}

function DetailDrawer({ row, sourceIds, onClose }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!row) return;
    setLoading(true);
    const params = { days: 180 };
    if (sourceIds?.length) params.source_ids = sourceIds.join(',');
    api.getDemandSignalDetail(row.label, params)
      .then(setSignals)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [row?.label, sourceIds?.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!row) return null;

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 300, display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end' }}
      onClick={onClose}
    >
      <div
        style={{ background: '#fff', width: '100%', maxWidth: 560, height: '100vh', overflowY: 'auto', padding: 24, boxShadow: '-4px 0 20px rgba(0,0,0,0.12)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: '#525252', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Demand Signal</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#161616', lineHeight: 1.3 }}>
                  {row.display_label || row.label}
                </div>
                <div style={{ fontSize: 11, color: '#8d8d8d', marginTop: 2, fontFamily: 'monospace' }}>{row.label}</div>
          </div>
          <button onClick={onClose} style={{ fontSize: 20, cursor: 'pointer', color: '#525252', flexShrink: 0, marginLeft: 12 }}>✕</button>
        </div>

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16, padding: '12px 0', borderTop: '1px solid #e0e0e0', borderBottom: '1px solid #e0e0e0' }}>
          <div>
            <div style={{ fontSize: 11, color: '#8d8d8d' }}>SIGNALS</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#0f62fe' }}>{row.signal_count}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#8d8d8d' }}>PRACTITIONER EVIDENCE</div>
            <div style={{ fontSize: 16, marginTop: 4 }}><EvidenceBadge weight={row.evidence_weight_avg} /></div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#8d8d8d' }}>MOMENTUM</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#161616' }}>{row.momentum.toFixed(1)}</div>
          </div>
        </div>

        {/* Industries & Personas */}
        {row.industries?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 4 }}>INDUSTRIES</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {row.industries.map(i => (
                <span key={i} style={{ background: '#edf5ff', color: '#0043ce', padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>{i}</span>
              ))}
            </div>
          </div>
        )}
        {row.personas?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 4 }}>PERSONAS</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {row.personas.map(p => (
                <span key={p} style={{ background: '#f4f4f4', color: '#262626', padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>{p}</span>
              ))}
            </div>
          </div>
        )}

        {/* Sample problems */}
        {row.sample_problems?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 6 }}>WHAT PRACTITIONERS STRUGGLE WITH</div>
            {row.sample_problems.map((p, i) => (
              <div key={i} style={{ fontSize: 13, color: '#161616', marginBottom: 6, paddingLeft: 10, borderLeft: '3px solid #fa4d56', lineHeight: 1.5 }}>{p}</div>
            ))}
          </div>
        )}

        {/* Sample outcomes */}
        {row.sample_outcomes?.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 6 }}>WHAT THEY WANT TO ACHIEVE</div>
            {row.sample_outcomes.map((o, i) => (
              <div key={i} style={{ fontSize: 13, color: '#161616', marginBottom: 6, paddingLeft: 10, borderLeft: '3px solid #24a148', lineHeight: 1.5 }}>{o}</div>
            ))}
          </div>
        )}

        {/* Source signals */}
        <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 8 }}>CONTRIBUTING SIGNALS ({signals.length})</div>
        {loading ? (
          <div style={{ color: '#8d8d8d', fontSize: 13 }}>Loading…</div>
        ) : signals.length === 0 ? (
          <div style={{ color: '#8d8d8d', fontSize: 13 }}>No signals found.</div>
        ) : signals.map(s => (
          <div key={s.id} style={{ borderTop: '1px solid #e0e0e0', paddingTop: 10, paddingBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 11, color: '#8d8d8d' }}>{SOURCE_TYPE_LABELS[s.source_type] || s.source_type}</span>
              <span style={{ fontSize: 11, color: '#c6c6c6' }}>·</span>
              <span style={{ fontSize: 11, color: '#8d8d8d' }}>{s.source_name}</span>
              {s.author_type === 'practitioner' && (
                <span style={{ fontSize: 10, background: '#defbe6', color: '#198038', padding: '1px 6px', borderRadius: 8 }}>👷 Practitioner</span>
              )}
              {s.author_type === 'vendor' && (
                <span style={{ fontSize: 10, background: '#fff1f1', color: '#da1e28', padding: '1px 6px', borderRadius: 8 }}>🏢 Vendor</span>
              )}
              <EvidenceBadge weight={s.evidence_weight} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#161616', marginBottom: 4, lineHeight: 1.4 }}>
              {s.url ? (
                <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ color: '#161616', textDecoration: 'none' }}
                  onMouseEnter={e => e.currentTarget.style.color = '#0f62fe'}
                  onMouseLeave={e => e.currentTarget.style.color = '#161616'}>
                  {s.title}
                </a>
              ) : s.title}
            </div>
            {s.problem && (
              <div style={{ fontSize: 12, color: '#525252', lineHeight: 1.5 }}>
                <em>Problem:</em> {s.problem}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DemandSignalRadar({ sourceIds }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [days, setDays] = useState(180);
  const [authorFilter, setAuthorFilter] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    const params = { days, limit: 30 };
    if (sourceIds?.length) params.source_ids = sourceIds.join(',');
    if (authorFilter) params.author_type = authorFilter;
    api.getDemandSignals(params)
      .then(setRows)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days, authorFilter, sourceIds?.join(',')]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const maxMomentum = rows.reduce((m, r) => Math.max(m, r.momentum), 0);

  return (
    <>
      <div className="chart-panel">
        <div className="chart-header">
          <span className="section-title">Demand Signal Radar</span>
          <span className="section-meta">{rows.length} patterns · practitioner-led market demand</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              className="feed-select"
              value={authorFilter}
              onChange={e => setAuthorFilter(e.target.value)}
            >
              <option value="">All authors</option>
              <option value="practitioner">👷 Practitioners only</option>
              <option value="vendor">🏢 Vendors only</option>
            </select>
            <select
              className="feed-select"
              value={days}
              onChange={e => setDays(Number(e.target.value))}
            >
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last 12 months</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="empty-state"><div className="spinner" /><div>Loading demand signals…</div></div>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <div>No demand signals yet.</div>
            <div style={{ fontSize: 12, color: '#8d8d8d', marginTop: 4 }}>
              Run "AI Re-enrich" to extract demand patterns from existing signals.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="demand-table">
              <thead>
                <tr>
                  <th>Demand Signal</th>
                  <th>Momentum</th>
                  <th>Practitioner Evidence</th>
                  <th>Industries</th>
                  <th>Signals</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={row.label}
                    className="demand-row"
                    onClick={() => setSelected(row)}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: '#8d8d8d', fontSize: 11, minWidth: 18, fontVariantNumeric: 'tabular-nums' }}>
                          {i + 1}
                        </span>
                        <span style={{ fontWeight: 600, color: '#161616', fontSize: 13 }}>
                          {row.display_label || row.label}
                        </span>
                      </div>
                      {row.sample_problems?.[0] && (
                        <div style={{ fontSize: 11, color: '#525252', marginTop: 2, paddingLeft: 26, lineHeight: 1.4 }}>
                          {row.sample_problems[0].slice(0, 120)}{row.sample_problems[0].length > 120 ? '…' : ''}
                        </div>
                      )}
                    </td>
                    <td><MomentumBar value={row.momentum} max={maxMomentum} /></td>
                    <td><EvidenceBadge weight={row.evidence_weight_avg} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {(row.industries || []).slice(0, 3).map(ind => (
                          <span key={ind} style={{ background: '#edf5ff', color: '#0043ce', padding: '1px 6px', borderRadius: 8, fontSize: 11 }}>{ind}</span>
                        ))}
                        {(row.industries || []).length > 3 && (
                          <span style={{ color: '#8d8d8d', fontSize: 11 }}>+{row.industries.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center', fontWeight: 700, color: '#0f62fe' }}>{row.signal_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <DetailDrawer
        row={selected}
        sourceIds={sourceIds}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
