import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';

const SOURCE_TYPE_ICONS = {
  practitioner_community: '👷',
  practitioner_pub:       '📖',
  conference:             '🎤',
  trade_media:            '📰',
  rss:                    '📊',
  // legacy aliases
  reddit:                 '👷',
  community:              '👷',
  industry_news:          '📰',
};

const SOURCE_TYPE_LABELS = {
  practitioner_community: 'Practitioner Communities',
  practitioner_pub:       'Practitioner Publications',
  conference:             'Conference Programs',
  trade_media:            'Trade Media',
  rss:                    'Analyst Feeds',
  // legacy aliases
  reddit:                 'Practitioner Communities',
  community:              'Practitioner Communities',
  industry_news:          'Trade Media',
};

// Display order for groups (practitioner-first)
const TYPE_ORDER = [
  'practitioner_community',
  'practitioner_pub',
  'conference',
  'trade_media',
  'rss',
  // legacy
  'reddit',
  'community',
  'industry_news',
];

function GroupCheckbox({ checked, indeterminate, onChange }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={onChange}
      style={{ accentColor: 'var(--ibm-blue)', width: 14, height: 14, flexShrink: 0, cursor: 'pointer' }}
    />
  );
}

export function SourceFilter({ onFilterChange }) {
  const [sources, setSources]   = useState([]);
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    api.getSources().then(data => {
      setSources(data);
      const enabledIds = new Set(data.filter(s => s.enabled).map(s => s.id));
      setSelected(enabledIds);
      onFilterChange([...enabledIds]);
    }).catch(console.error);
  }, []);                                 // eslint-disable-line react-hooks/exhaustive-deps

  const toggleOne = useCallback((id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      onFilterChange([...next]);
      return next;
    });
  }, [onFilterChange]);

  const toggleGroup = useCallback((type) => {
    const typeIds = sources.filter(s => s.source_type === type).map(s => s.id);
    const allOn   = typeIds.every(id => selected.has(id));
    setSelected(prev => {
      const next = new Set(prev);
      typeIds.forEach(id => allOn ? next.delete(id) : next.add(id));
      onFilterChange([...next]);
      return next;
    });
  }, [sources, selected, onFilterChange]);

  const grouped = sources.reduce((acc, s) => {
    (acc[s.source_type] = acc[s.source_type] || []).push(s);
    return acc;
  }, {});

  const orderedTypes = [
    ...TYPE_ORDER.filter(t => grouped[t]),
    ...Object.keys(grouped).filter(t => !TYPE_ORDER.includes(t)),
  ];

  return (
    <div className="sidebar-section">
      <div className="sidebar-label">Signal Sources</div>

      {orderedTypes.map(type => {
        const items   = grouped[type];
        const typeIds = items.map(s => s.id);
        const numOn   = typeIds.filter(id => selected.has(id)).length;
        const allOn   = numOn === typeIds.length;
        const someOn  = numOn > 0 && !allOn;

        return (
          <div key={type} className="source-filter-group">
            <div className="source-type-header">
              <GroupCheckbox
                checked={allOn}
                indeterminate={someOn}
                onChange={() => toggleGroup(type)}
              />
              <span>{SOURCE_TYPE_ICONS[type] || '🔗'}</span>
              <span
                style={{ cursor: 'pointer', userSelect: 'none' }}
                onClick={() => toggleGroup(type)}
              >
                {SOURCE_TYPE_LABELS[type] || type}
              </span>
              <span className="source-count-badge">
                {numOn}/{typeIds.length}
              </span>
            </div>

            {items.map(s => (
              <label
                key={s.id}
                className={`source-item ${!selected.has(s.id) ? 'disabled' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(s.id)}
                  onChange={() => toggleOne(s.id)}
                />
                <span className="source-item-name">{s.name}</span>
              </label>
            ))}
          </div>
        );
      })}
    </div>
  );
}
