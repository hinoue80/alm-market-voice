import { useState, useEffect } from 'react';
import { api } from '../api';

/**
 * MergeTool — lets admins collapse near-duplicate demand signal labels.
 * Lives in the sidebar under a collapsible "Manage Signals" section.
 */
export function MergeTool({ onMerged }) {
  const [open, setOpen] = useState(false);
  const [labels, setLabels] = useState([]);
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {merged, source, target} or {error}

  const load = () => {
    api.getDemandSignalLabels()
      .then(setLabels)
      .catch(() => {});
  };

  useEffect(() => {
    if (open) load();
  }, [open]);

  const handleMerge = async () => {
    if (!source || !target || source === target) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await api.mergeDemandSignals(source, target);
      setResult(r);
      setSource('');
      load(); // refresh labels
      onMerged?.(); // tell parent to refresh radar
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ borderTop: '1px solid #e0e0e0', marginTop: 12, paddingTop: 12 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 11, fontWeight: 600, color: '#525252',
          textTransform: 'uppercase', letterSpacing: '0.05em',
          display: 'flex', alignItems: 'center', gap: 6, padding: 0,
          width: '100%',
        }}
      >
        <span>{open ? '▾' : '▸'}</span> Manage Signals
      </button>

      {open && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 11, color: '#8d8d8d', marginBottom: 8, lineHeight: 1.5 }}>
            Merge near-duplicate demand signal labels. All signals tagged with
            the <em>source</em> label will be reassigned to the <em>target</em>.
          </div>

          <label style={{ fontSize: 11, fontWeight: 600, color: '#525252', display: 'block', marginBottom: 3 }}>
            Merge FROM (remove)
          </label>
          <select
            value={source}
            onChange={e => setSource(e.target.value)}
            style={{ width: '100%', fontSize: 12, padding: '4px 6px', marginBottom: 8, border: '1px solid #c6c6c6', borderRadius: 3 }}
          >
            <option value="">— select label —</option>
            {labels.filter(l => l.label !== target).map(l => (
              <option key={l.label} value={l.label}>{l.display_label}</option>
            ))}
          </select>

          <label style={{ fontSize: 11, fontWeight: 600, color: '#525252', display: 'block', marginBottom: 3 }}>
            Merge INTO (keep)
          </label>
          <select
            value={target}
            onChange={e => setTarget(e.target.value)}
            style={{ width: '100%', fontSize: 12, padding: '4px 6px', marginBottom: 10, border: '1px solid #c6c6c6', borderRadius: 3 }}
          >
            <option value="">— select label —</option>
            {labels.filter(l => l.label !== source).map(l => (
              <option key={l.label} value={l.label}>{l.display_label}</option>
            ))}
          </select>

          <button
            onClick={handleMerge}
            disabled={busy || !source || !target || source === target}
            style={{
              background: source && target && source !== target ? '#0f62fe' : '#c6c6c6',
              color: '#fff',
              border: 'none',
              borderRadius: 3,
              padding: '5px 12px',
              fontSize: 12,
              cursor: source && target && source !== target ? 'pointer' : 'not-allowed',
              width: '100%',
            }}
          >
            {busy ? 'Merging…' : '⇢ Merge'}
          </button>

          {result && !result.error && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#198038', lineHeight: 1.5 }}>
              ✓ Merged {result.merged} signal{result.merged !== 1 ? 's' : ''} from
              <em> {result.source}</em> into <em>{result.target}</em>.
            </div>
          )}
          {result?.error && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#da1e28' }}>
              ✗ {result.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
