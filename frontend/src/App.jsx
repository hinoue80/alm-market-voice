import { useState, useCallback, useEffect } from 'react';
import './index.css';
import './App.css';
import { SourceFilter } from './components/SourceFilter';
import { DemandSignalRadar } from './components/DemandSignalRadar';
import { SignalFeed } from './components/SignalFeed';
import { SummaryCards } from './components/SummaryCards';
import { TopicChart } from './components/TopicChart';
import { MergeTool } from './components/MergeTool';
import { api } from './api';

function Toast({ message, type, onClose }) {
  if (!message) return null;
  return (
    <div className={`toast toast-${type}`} onClick={onClose}>
      {message} <span style={{ marginLeft: 8, opacity: 0.7 }}>✕</span>
    </div>
  );
}

// ── Enrichment progress banner (auto-polls, auto-hides) ──────────────────────
function EnrichmentBanner({ onComplete }) {
  const [status, setStatus] = useState(null);
  const [notified, setNotified] = useState(false);

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await api.getReenrichStatus();
        setStatus(s);
      } catch (_) {}
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fire onComplete exactly once when enrichment transitions to 'complete'
  useEffect(() => {
    if (status?.status === 'complete' && !notified) {
      setNotified(true);
      onComplete?.();
    }
  }, [status?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!status || status.status === 'idle' || status.total === 0) return null;

  const pct = status.total > 0 ? Math.round((status.done / status.total) * 100) : 0;
  const isDone = status.status === 'complete';

  return (
    <div style={{
      background: isDone ? '#defbe6' : '#edf5ff',
      borderBottom: `1px solid ${isDone ? '#24a148' : '#0f62fe'}`,
      padding: '6px 24px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      fontSize: 12,
      color: isDone ? '#198038' : '#0043ce',
    }}>
      {isDone ? (
        <>✓ AI enrichment complete — {status.done} signals enriched. Radar updated automatically.</>
      ) : (
        <>
          <span>✦ AI enrichment in progress —</span>
          <div style={{ width: 120, height: 4, background: 'rgba(15,98,254,0.2)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${pct}%`, background: '#0f62fe', borderRadius: 2, transition: 'width 0.5s' }} />
          </div>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>{status.done}/{status.total} ({pct}%)</span>
          <span style={{ color: '#525252' }}>· Demand Signal Radar updates automatically</span>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [activeSourceIds, setActiveSourceIds] = useState([]);
  const [ingesting, setIngesting] = useState(false);
  const [reenriching, setReenriching] = useState(false);
  const [toast, setToast] = useState(null);
  const [enrichProvider, setEnrichProvider] = useState(null);
  const [radarKey, setRadarKey] = useState(0); // increment to force radar reload
  const [topicFilter, setTopicFilter] = useState('');

  useEffect(() => {
    api.getEnrichProviders()
      .then(p => setEnrichProvider(p))
      .catch(() => {/* backend not yet running */});
  }, []);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  };

  const handleFilterChange = useCallback((ids) => {
    setActiveSourceIds(ids);
  }, []);

  const triggerIngestion = async () => {
    setIngesting(true);
    showToast('Ingestion started — this runs in the background. Check back in a few minutes.', 'info');
    try {
      await api.triggerIngestion();
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const status = await api.getIngestionStatus();
          if (status.status === 'complete') {
            clearInterval(poll);
            setIngesting(false);
            showToast(
              `✓ Ingestion complete — ${status.total_saved} new signals saved from ${status.sources_processed} sources.`,
              'success'
            );
          } else if (status.status === 'error') {
            clearInterval(poll);
            setIngesting(false);
            showToast(`Ingestion error: ${status.error}`, 'error');
          } else if (attempts > 120) {
            clearInterval(poll);
            setIngesting(false);
            showToast('Ingestion is taking longer than expected — check logs.', 'info');
          }
        } catch (e) { /* ignore poll errors */ }
      }, 3000);
    } catch (e) {
      setIngesting(false);
      showToast(`Failed to start ingestion: ${e.message}`, 'error');
    }
  };

  const triggerReenrich = async () => {
    setReenriching(true);
    showToast('AI re-enrichment started — extracting demand signals from all content…', 'info');
    try {
      await api.triggerReenrich(300);
      const poll = setInterval(async () => {
        try {
          const s = await api.getReenrichStatus();
          if (s.status === 'complete') {
            clearInterval(poll);
            setReenriching(false);
            setRadarKey(k => k + 1); // auto-refresh radar
            showToast(`✓ AI enrichment complete — ${s.done} signals enriched.`, 'success');
          } else if (s.status === 'error') {
            clearInterval(poll);
            setReenriching(false);
            showToast(`Enrichment error: ${s.error}`, 'error');
          }
        } catch (_) {}
      }, 4000);
    } catch (e) {
      setReenriching(false);
      showToast(`Re-enrichment failed: ${e.message}`, 'error');
    }
  };

  return (
    <>
      {/* ── Header ── */}
      <header className="header">
        <div className="header-brand">
          <span className="header-logo">IBM</span>
          <div className="header-divider" />
          <span className="header-title">ALM Market Voice</span>
        </div>
        <span className="header-subtitle">
          Asset Lifecycle Management · Practitioner Demand Intelligence
        </span>
        <div className="header-actions">
          {enrichProvider && (
            <span className={`provider-badge provider-badge--${
              enrichProvider.active_provider === 'watsonx'   ? 'wx' :
              enrichProvider.active_provider === 'anthropic' ? 'claude' :
              enrichProvider.active_provider === 'openai'    ? 'oai' :
              enrichProvider.active_provider === 'ollama'    ? 'ollama' : 'fallback'
            }`}>
              {enrichProvider.active_provider === 'watsonx'   && '🔵 watsonx.ai'}
              {enrichProvider.active_provider === 'anthropic' && '🟣 Claude'}
              {enrichProvider.active_provider === 'openai'    && '🟢 OpenAI'}
              {enrichProvider.active_provider === 'ollama'    && '🦙 Ollama local'}
              {enrichProvider.active_provider === 'keyword_fallback' && '⚠ keyword fallback'}
            </span>
          )}
          <button
            className="btn btn-ghost"
            onClick={triggerReenrich}
            disabled={reenriching || ingesting}
            title="Re-run AI enrichment to extract demand signals, problems, outcomes, and author type"
          >
            {reenriching ? '✦ Enriching…' : '✦ AI Re-enrich'}
          </button>
          <button
            className="btn btn-ghost"
            onClick={triggerIngestion}
            disabled={ingesting || reenriching}
          >
            {ingesting ? '⟳ Ingesting…' : '⟳ Refresh Signals'}
          </button>
        </div>
      </header>

      {/* ── Enrichment banner (auto-polls, auto-hides when done) ── */}
      <EnrichmentBanner onComplete={() => setRadarKey(k => k + 1)} />

      {/* ── Body ── */}
      <div className="layout">
        {/* Sidebar — source filter */}
        <aside className="sidebar">
          <SourceFilter onFilterChange={handleFilterChange} />

          <div className="sidebar-section" style={{ marginTop: 8 }}>
            <div className="sidebar-label">About</div>
            <p style={{ fontSize: 11, color: 'var(--ibm-gray-50)', lineHeight: 1.6 }}>
              Signals are refreshed weekly every Monday at 06:00 UTC.
              Use "Refresh Signals" to run an immediate ingestion, then
              "AI Re-enrich" to extract demand patterns from new content.
            </p>
            <p style={{ fontSize: 11, color: 'var(--ibm-gray-50)', lineHeight: 1.6, marginTop: 6 }}>
              👷 = practitioner content (highest signal value) · 🏢 = vendor
            </p>
          </div>

          <MergeTool onMerged={() => setRadarKey(k => k + 1)} />
        </aside>

        {/* Main dashboard */}
        <main className="main">
          <SummaryCards sourceIds={activeSourceIds} />

          <DemandSignalRadar key={radarKey} sourceIds={activeSourceIds} />

          <TopicChart sourceIds={activeSourceIds} onTopicClick={setTopicFilter} />

          <SignalFeed sourceIds={activeSourceIds} topicFilter={topicFilter} />
        </main>
      </div>

      <Toast
        message={toast?.message}
        type={toast?.type}
        onClose={() => setToast(null)}
      />
    </>
  );
}
