import { useState, useEffect, useRef, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, LabelList,
} from 'recharts';
import { api } from '../api';

const SENTIMENT_COLORS = {
  positive: '#198038',
  neutral:  '#8d8d8d',
  negative: '#da1e28',
};

const TYPE_LABELS = {
  demand:      'Demand',
  complaint:   'Pain point',
  competitive: 'Competitive',
  analyst:     'Analyst',
  general:     'General',
};

function sentimentColor(score) {
  if (score >  0.2) return SENTIMENT_COLORS.positive;
  if (score < -0.2) return SENTIMENT_COLORS.negative;
  return SENTIMENT_COLORS.neutral;
}

// ── Popover shown when a bar is clicked ──────────────────────────────────────

function TopicPopover({ topic, data, signals, loading, onClose, onFilterClick }) {
  const ref = useRef(null);

  // Close on outside click
  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div ref={ref} className="topic-popover">
      {/* Header */}
      <div className="topic-popover-header">
        <span className="topic-popover-title">{topic}</span>
        <button className="topic-popover-close" onClick={onClose}>✕</button>
      </div>

      {/* Stats row */}
      <div className="topic-popover-stats">
        <span>{data.mention_count} mention{data.mention_count !== 1 ? 's' : ''}</span>
        <span style={{ color: sentimentColor(data.avg_sentiment) }}>
          {data.sentiment_label} sentiment
        </span>
        <button
          className="topic-popover-filter-btn"
          onClick={() => { onFilterClick(topic); onClose(); }}
        >
          Filter signals →
        </button>
      </div>

      {/* Representative signals */}
      <div className="topic-popover-signals-label">
        Recent signals mentioning this topic
      </div>
      {loading ? (
        <div className="topic-popover-loading">Loading…</div>
      ) : signals.length === 0 ? (
        <div className="topic-popover-loading">No signals found</div>
      ) : (
        <ul className="topic-popover-list">
          {signals.map((s, i) => (
            <li key={i} className="topic-popover-item">
              <div className="topic-popover-item-meta">
                <span className="topic-popover-source">{s.source_name}</span>
                <span className="topic-popover-date">{s.published_at}</span>
                {s.signal_type && s.signal_type !== 'general' && (
                  <span className={`topic-popover-type type-${s.signal_type}`}>
                    {TYPE_LABELS[s.signal_type] || s.signal_type}
                  </span>
                )}
              </div>
              <div className="topic-popover-item-title">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer">
                    {s.title}
                  </a>
                ) : s.title}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Custom bar shape that highlights on hover ─────────────────────────────────

function HoverBar(props) {
  const { x, y, width, height, fill, isHovered } = props;
  return (
    <rect
      x={x} y={y} width={width} height={height}
      fill={fill}
      opacity={isHovered ? 1 : 0.75}
      stroke={isHovered ? fill : 'none'}
      strokeWidth={isHovered ? 1.5 : 0}
      rx={2} ry={2}
      style={{ transition: 'opacity 0.1s' }}
    />
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function TopicChart({ sourceIds, onTopicClick }) {
  const [topics,       setTopics]       = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [weeks,        setWeeks]        = useState(4);
  const [hoveredTopic, setHoveredTopic] = useState(null);
  const [popover,      setPopover]      = useState(null);   // { topic, data, x, y }
  const [popSignals,   setPopSignals]   = useState([]);
  const [popLoading,   setPopLoading]   = useState(false);
  const chartRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    api.getTopics({ weeks, limit: 15 })
      .then(data => setTopics([...data].sort((a, b) => b.mention_count - a.mention_count)))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [weeks, sourceIds]);

  const openPopover = useCallback((topicData) => {
    setPopover(topicData);
    setPopSignals([]);
    setPopLoading(true);
    api.getTopicSignals(topicData.topic)
      .then(setPopSignals)
      .catch(console.error)
      .finally(() => setPopLoading(false));
  }, []);

  const closePopover = useCallback(() => setPopover(null), []);

  if (loading) {
    return (
      <div className="topics-panel">
        <div className="empty-state"><div className="spinner" /><div>Loading topics…</div></div>
      </div>
    );
  }

  if (!topics.length) {
    return (
      <div className="topics-panel">
        <div className="section-header">
          <span className="section-title">Trending Topics</span>
        </div>
        <div className="empty-state">No topics found. Run an ingestion to populate data.</div>
      </div>
    );
  }

  // Chart height: 28px per bar + padding
  const chartHeight = Math.max(220, topics.length * 34 + 20);

  return (
    <div className="topics-panel" style={{ position: 'relative' }}>
      <div className="section-header">
        <span className="section-title">🔥 Trending Topics</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="section-meta">past</span>
          <select
            className="feed-select"
            value={weeks}
            onChange={e => setWeeks(Number(e.target.value))}
          >
            <option value={1}>1 week</option>
            <option value={4}>4 weeks</option>
            <option value={8}>8 weeks</option>
            <option value={12}>12 weeks</option>
          </select>
          <span className="section-meta" style={{ marginLeft: 4 }}>
            Click a bar for details
          </span>
        </div>
      </div>

      <div ref={chartRef} style={{ position: 'relative' }}>
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={topics}
            layout="vertical"
            margin={{ top: 0, right: 52, left: 0, bottom: 0 }}
            onClick={({ activePayload }) => {
              if (activePayload?.[0]) openPopover(activePayload[0].payload);
            }}
            onMouseMove={({ activePayload }) => {
              setHoveredTopic(activePayload?.[0]?.payload?.topic ?? null);
            }}
            onMouseLeave={() => setHoveredTopic(null)}
            style={{ cursor: 'pointer' }}
          >
            <XAxis type="number" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              type="category"
              dataKey="topic"
              width={200}
              tick={({ x, y, payload }) => {
                const isHov = payload.value === hoveredTopic;
                return (
                  <text
                    x={x} y={y} dy={4}
                    textAnchor="end"
                    fontSize={12}
                    fill={isHov ? '#0043ce' : '#161616'}
                    fontWeight={isHov ? 600 : 400}
                    style={{ transition: 'fill 0.1s' }}
                  >
                    {payload.value}
                  </text>
                );
              }}
              axisLine={false}
              tickLine={false}
            />
            <Bar
              dataKey="mention_count"
              maxBarSize={22}
              shape={(props) => {
                const isHov = props.topic === hoveredTopic;
                return <HoverBar {...props} fill={sentimentColor(props.avg_sentiment)} isHovered={isHov} />;
              }}
            >
              {topics.map((entry, i) => (
                <Cell key={i} fill={sentimentColor(entry.avg_sentiment)} />
              ))}
              <LabelList
                dataKey="mention_count"
                position="right"
                style={{ fontSize: 11, fill: '#525252' }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {/* Popover */}
        {popover && (
          <TopicPopover
            topic={popover.topic}
            data={popover}
            signals={popSignals}
            loading={popLoading}
            onClose={closePopover}
            onFilterClick={onTopicClick}
          />
        )}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, color: '#8d8d8d', justifyContent: 'center', flexWrap: 'wrap' }}>
        <span style={{ color: SENTIMENT_COLORS.positive }}>■ Positive sentiment</span>
        <span style={{ color: SENTIMENT_COLORS.neutral }}>■ Neutral</span>
        <span style={{ color: SENTIMENT_COLORS.negative }}>■ Negative sentiment</span>
      </div>
    </div>
  );
}
