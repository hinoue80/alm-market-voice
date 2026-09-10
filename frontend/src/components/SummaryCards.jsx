import { useState, useEffect } from 'react';
import { api } from '../api';

export function SummaryCards({ sourceIds }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    Promise.all([
      api.getSignals({ days: 7,  page_size: 1, ...(sourceIds?.length && { source_ids: sourceIds.join(',') }) }),
      api.getSignals({ days: 30, page_size: 1, ...(sourceIds?.length && { source_ids: sourceIds.join(',') }) }),
      api.getTopics({ weeks: 4, limit: 50 }),
      api.getSignals({ days: 30, signal_type: 'demand', page_size: 1, ...(sourceIds?.length && { source_ids: sourceIds.join(',') }) }),
    ]).then(([week, month, topics, demand]) => {
      setData({
        thisWeek: week.total,
        thisMonth: month.total,
        topTopics: topics.length,
        demandSignals: demand.total,
      });
    }).catch(console.error);
  }, [sourceIds]);

  const cards = data ? [
    { value: data.thisWeek,     label: 'Signals this week' },
    { value: data.thisMonth,    label: 'Signals this month' },
    { value: data.topTopics,    label: 'Trending topics' },
    { value: data.demandSignals, label: 'Demand signals (30d)' },
  ] : Array(4).fill({ value: '…', label: '' });

  return (
    <div className="cards-row">
      {cards.map((c, i) => (
        <div key={i} className="card">
          <div className="card-value">{c.value}</div>
          <div className="card-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
