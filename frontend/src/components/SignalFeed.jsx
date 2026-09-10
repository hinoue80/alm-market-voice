import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

const SOURCE_TYPE_ICONS = {
  practitioner_community: '👷',
  practitioner_pub:       '📖',
  conference:             '🎤',
  trade_media:            '📰',
  rss:                    '📊',
  reddit:                 '👷',
  community:              '👷',
  industry_news:          '📰',
};

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function SentimentBadge({ value }) {
  return <span className={`badge badge-${value}`}>{value}</span>;
}

function SignalTypeBadge({ value }) {
  const labels = {
    demand:    '🎯 demand',
    complaint: '⚠️ complaint',
    analyst:   '📑 analyst',
    general:   'general',
  };
  return <span className={`badge badge-${value}`}>{labels[value] || value}</span>;
}

function AuthorBadge({ authorType }) {
  if (authorType === 'practitioner') {
    return (
      <span style={{ fontSize: 11, background: '#defbe6', color: '#198038', padding: '1px 6px', borderRadius: 8 }}>
        👷 Practitioner
      </span>
    );
  }
  if (authorType === 'vendor') {
    return (
      <span style={{ fontSize: 11, background: '#fff1f1', color: '#da1e28', padding: '1px 6px', borderRadius: 8 }}>
        🏢 Vendor
      </span>
    );
  }
  return null;
}

function EvidenceStars({ weight }) {
  const w = Math.round(weight || 0);
  return (
    <span style={{ color: w >= 3 ? '#f1c21b' : '#c6c6c6', fontSize: 12, letterSpacing: 1 }}
      title={`Evidence weight ${w}/5`}>
      {'★'.repeat(w)}{'☆'.repeat(5 - w)}
    </span>
  );
}

function SignalModal({ signal, onClose }) {
  if (!signal) return null;
  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
      onClick={onClose}
    >
      <div
        style={{ background: '#fff', borderRadius: 4, padding: 24, maxWidth: 640, width: '100%', maxHeight: '85vh', overflow: 'auto' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="signal-source">
              {SOURCE_TYPE_ICONS[signal.source_type] || '🔗'} {signal.source_name}
            </span>
            <AuthorBadge authorType={signal.author_type} />
            <EvidenceStars weight={signal.evidence_weight} />
          </div>
          <button onClick={onClose} style={{ fontSize: 18, cursor: 'pointer', color: '#525252' }}>✕</button>
        </div>

        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8, lineHeight: 1.4 }}>{signal.title}</div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          <SentimentBadge value={signal.sentiment} />
          <SignalTypeBadge value={signal.signal_type} />
          {signal.industry && signal.industry !== 'unknown' && (
            <span style={{ background: '#edf5ff', color: '#0043ce', padding: '2px 8px', borderRadius: 10, fontSize: 11 }}>
              {signal.industry}
            </span>
          )}
          {signal.persona && signal.persona !== 'unknown' && (
            <span style={{ background: '#f4f4f4', color: '#262626', padding: '2px 8px', borderRadius: 10, fontSize: 11 }}>
              {signal.persona}
            </span>
          )}
          <span style={{ fontSize: 11, color: '#8d8d8d', alignSelf: 'center' }}>{formatDate(signal.published_at)}</span>
        </div>

        {/* Demand signal pattern */}
        {signal.demand_signal && (
          <div style={{ background: '#f4f4f4', borderRadius: 4, padding: '8px 12px', marginBottom: 12, fontSize: 13 }}>
            <span style={{ fontWeight: 600, color: '#525252', fontSize: 11, marginRight: 6 }}>DEMAND SIGNAL</span>
            <span style={{ color: '#161616' }}>{signal.demand_signal}</span>
          </div>
        )}

        {/* Problem / Outcome / Approach */}
        {signal.problem && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#da1e28', marginBottom: 2 }}>PROBLEM</div>
            <div style={{ fontSize: 13, color: '#161616', lineHeight: 1.5, paddingLeft: 10, borderLeft: '3px solid #fa4d56' }}>
              {signal.problem}
            </div>
          </div>
        )}
        {signal.desired_outcome && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#198038', marginBottom: 2 }}>DESIRED OUTCOME</div>
            <div style={{ fontSize: 13, color: '#161616', lineHeight: 1.5, paddingLeft: 10, borderLeft: '3px solid #24a148' }}>
              {signal.desired_outcome}
            </div>
          </div>
        )}
        {signal.approach && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#0f62fe', marginBottom: 2 }}>APPROACH</div>
            <div style={{ fontSize: 13, color: '#161616', lineHeight: 1.5, paddingLeft: 10, borderLeft: '3px solid #0f62fe' }}>
              {signal.approach}
            </div>
          </div>
        )}

        {/* Body preview */}
        {signal.body_preview && (
          <div style={{ fontSize: 13, color: '#262626', lineHeight: 1.6, marginBottom: 12, whiteSpace: 'pre-wrap', borderTop: '1px solid #e0e0e0', paddingTop: 12 }}>
            {signal.body_preview}
          </div>
        )}

        {signal.topics?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: '#8d8d8d', marginBottom: 4 }}>TOPICS</div>
            <div className="signal-topics">
              {signal.topics.map(t => <span key={t} className="topic-tag">{t}</span>)}
            </div>
          </div>
        )}

        {signal.url && (
          <a href={signal.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm" style={{ display: 'inline-flex' }}>
            View original →
          </a>
        )}
      </div>
    </div>
  );
}

export function SignalFeed({ sourceIds, topicFilter }) {
  const [signals, setSignals] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [sentiment, setSentiment] = useState('');
  const [signalType, setSignalType] = useState('');
  const [authorType, setAuthorType] = useState('');
  const [days, setDays] = useState(90);
  const [activeTopic, setActiveTopic] = useState(topicFilter || '');
  const [selected, setSelected] = useState(null);

  useEffect(() => setActiveTopic(topicFilter || ''), [topicFilter]);

  const PAGE_SIZE = 20;

  const load = useCallback(() => {
    setLoading(true);
    const params = {
      page,
      page_size: PAGE_SIZE,
      days,
      ...(sentiment   && { sentiment }),
      ...(signalType  && { signal_type: signalType }),
      ...(authorType  && { author_type: authorType }),
      ...(activeTopic && { topic: activeTopic }),
      ...(sourceIds?.length && { source_ids: sourceIds.join(',') }),
    };
    api.getSignals(params)
      .then(data => { setSignals(data.results); setTotal(data.total); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page, days, sentiment, signalType, authorType, activeTopic, sourceIds]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [sentiment, signalType, authorType, days, activeTopic, sourceIds]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <>
      <div className="feed-panel">
        <div className="feed-toolbar">
          <span className="section-title" style={{ fontSize: 14 }}>Signal Feed</span>
          <span className="section-meta">{total.toLocaleString()} signals</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {activeTopic && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#edf5ff', color: '#0f62fe', padding: '2px 8px', borderRadius: 10, fontSize: 12 }}>
                🏷️ {activeTopic}
                <button onClick={() => setActiveTopic('')} style={{ fontSize: 14, lineHeight: 1, marginLeft: 2 }}>✕</button>
              </span>
            )}
            <select className="feed-select" value={days} onChange={e => setDays(Number(e.target.value))}>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={60}>Last 60 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
            </select>
            <select className="feed-select" value={authorType} onChange={e => setAuthorType(e.target.value)}>
              <option value="">All authors</option>
              <option value="practitioner">👷 Practitioners</option>
              <option value="vendor">🏢 Vendors</option>
            </select>
            <select className="feed-select" value={sentiment} onChange={e => setSentiment(e.target.value)}>
              <option value="">All sentiments</option>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="negative">Negative</option>
            </select>
            <select className="feed-select" value={signalType} onChange={e => setSignalType(e.target.value)}>
              <option value="">All types</option>
              <option value="demand">Demand</option>
              <option value="complaint">Complaint</option>
              <option value="analyst">Analyst</option>
              <option value="general">General</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="empty-state"><div className="spinner" /><div>Loading signals…</div></div>
        ) : signals.length === 0 ? (
          <div className="empty-state">No signals match the current filters.</div>
        ) : (
          signals.map(s => (
            <div key={s.id} className="signal-row" onClick={() => setSelected(s)}>
              <div className="signal-meta">
                <span className="signal-source">
                  {SOURCE_TYPE_ICONS[s.source_type] || '🔗'} {s.source_name}
                </span>
                <span style={{ color: 'var(--ibm-gray-30)', fontSize: 11 }}>·</span>
                <span className="signal-date">{formatDate(s.published_at)}</span>
                <AuthorBadge authorType={s.author_type} />
                <EvidenceStars weight={s.evidence_weight} />
                <SentimentBadge value={s.sentiment} />
                <SignalTypeBadge value={s.signal_type} />
              </div>

              <div className="signal-title">{s.title}</div>

              {/* Show problem field if available, otherwise body preview */}
              {s.problem ? (
                <div style={{ fontSize: 12, color: '#525252', marginTop: 2, lineHeight: 1.5, paddingLeft: 10, borderLeft: '3px solid #fa4d56' }}>
                  {s.problem.slice(0, 200)}{s.problem.length > 200 ? '…' : ''}
                </div>
              ) : s.body_preview ? (
                <div className="signal-body">{s.body_preview}</div>
              ) : null}

              {s.topics?.length > 0 && (
                <div className="signal-topics">
                  {s.topics.map(t => (
                    <span
                      key={t}
                      className="topic-tag"
                      onClick={e => { e.stopPropagation(); setActiveTopic(t); }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <button className="page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span className="page-info">Page {page} of {totalPages}</span>
            <button className="page-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        )}
      </div>

      <SignalModal signal={selected} onClose={() => setSelected(null)} />
    </>
  );
}
