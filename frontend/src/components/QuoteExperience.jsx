import { useCallback, useMemo, useState } from 'react';
import { useDataChannel, useRoomContext, useVoiceAssistant } from '@livekit/components-react';

import QuoteCarousel from './QuoteCarousel.jsx';
import QuoteTable from './QuoteTable.jsx';
import './QuoteExperience.css';

const QUOTE_UI_TOPIC = 'quote.ui';
const QUOTE_SUBMIT_RPC = 'quote.submit';
// Screenshots are served by the FastAPI backend, not the Vite dev server.
// Baked in at build time by Vite; docker-compose passes it as a build arg.
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001';

function QuoteForm({ fields, values, onChange, onSubmit, busy }) {
  return (
    <form
      className="quote-card quote-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit('confirm');
      }}
    >
      <header className="quote-card__head">
        <h2>Confirm your details</h2>
        <p>Change anything that isn&apos;t right, then confirm to get your rate.</p>
      </header>

      <div className="quote-form__grid">
        {fields.map((field) => (
          <label
            key={field.key}
            className={`quote-field quote-field--${field.type}`}
            htmlFor={`qf-${field.key}`}
          >
            <span className="quote-field__label">
              {field.label}
              {field.optional && <em className="quote-field__opt">optional</em>}
            </span>

            {field.type === 'select' ? (
              <select
                id={`qf-${field.key}`}
                value={values[field.key] ?? ''}
                onChange={(event) => onChange(field.key, event.target.value)}
              >
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : field.type === 'boolean' ? (
              <input
                id={`qf-${field.key}`}
                type="checkbox"
                checked={Boolean(values[field.key])}
                onChange={(event) => onChange(field.key, event.target.checked)}
              />
            ) : (
              <input
                id={`qf-${field.key}`}
                type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}
                value={values[field.key] ?? ''}
                onChange={(event) => onChange(field.key, event.target.value)}
              />
            )}

            {field.hint && <span className="quote-field__hint">{field.hint}</span>}
          </label>
        ))}
      </div>

      <footer className="quote-card__actions">
        <button type="button" className="quote-btn" onClick={() => onSubmit('cancel')} disabled={busy}>
          Not yet
        </button>
        <button type="submit" className="quote-btn quote-btn--primary" disabled={busy}>
          Confirm &amp; get my rate
        </button>
      </footer>
    </form>
  );
}

const money = (value) =>
  typeof value === 'number'
    ? new Intl.NumberFormat('en-CA', {
        style: 'currency',
        currency: 'CAD',
        maximumFractionDigits: 0,
      }).format(value)
    : null;

function QuoteLoading({ channels = [], done = 0, total = 0, landed = [] }) {
  // Each channel reports as it lands, so the list resolves in place rather than
  // animating a fake sequence. Anything not yet reported stays pending.
  const byName = new Map(landed.map((q) => [q.channel_name, q]));
  const pct = total ? Math.round((done / total) * 100) : 0;

  return (
    <div className="quote-card quote-loading">
      <div className="quote-loading__orb" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <h2>Checking {total || channels.length || 'all'} sources</h2>
      <p className="quote-loading__step">
        {done > 0 ? `${done} of ${total} back` : 'Entering your details on each site…'}
      </p>

      {channels.length > 0 && (
        <ul className="quote-loading__channels">
          {channels.map((name) => {
            const hit = byName.get(name);
            const priced = hit && typeof hit.annual_premium === 'number';
            return (
              <li
                key={name}
                className={hit ? (priced ? 'is-done' : 'is-empty') : 'is-pending'}
              >
                {name}
                {priced && <b>{money(hit.annual_premium)}</b>}
                {hit && !priced && <b>—</b>}
              </li>
            );
          })}
        </ul>
      )}

      <div className="quote-loading__track" aria-hidden="true">
        <div
          className={total ? 'quote-loading__bar is-determinate' : 'quote-loading__bar'}
          style={total ? { width: `${pct}%` } : undefined}
        />
      </div>
    </div>
  );
}

export default function QuoteExperience() {
  const room = useRoomContext();
  const { agent } = useVoiceAssistant();
  const [ui, setUi] = useState({ phase: 'idle' });
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState('cards');
  const [landed, setLanded] = useState([]);
  const [progress, setProgress] = useState({ done: 0, total: 0 });

  useDataChannel(QUOTE_UI_TOPIC, (msg) => {
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(msg.payload));
    } catch (err) {
      console.error('Unreadable quote UI message', err);
      return;
    }

    if (payload.phase === 'progress') {
      // Progress messages update the loading list without replacing the phase.
      setProgress({ done: payload.done, total: payload.total });
      setLanded((prev) =>
        prev.some((q) => q.channel_id === payload.quote.channel_id)
          ? prev
          : [...prev, payload.quote],
      );
      return;
    }

    setUi(payload);
    if (payload.phase === 'loading') {
      setLanded([]);
      setProgress({ done: 0, total: (payload.channels ?? []).length });
    }
    if (payload.phase === 'result') setView('cards');
    if (payload.phase === 'form') {
      setValues(payload.values ?? {});
      setBusy(false);
    }
  });

  const handleChange = useCallback((key, value) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSubmit = useCallback(
    async (action) => {
      // The form only ever appears because the agent published it, so if
      // useVoiceAssistant hasn't resolved yet the sole remote peer is the agent.
      const destinationIdentity =
        agent?.identity ?? [...room.remoteParticipants.values()][0]?.identity;

      if (!destinationIdentity) {
        console.error('No agent participant to submit the quote form to');
        return;
      }

      setBusy(true);
      try {
        await room.localParticipant.performRpc({
          destinationIdentity,
          method: QUOTE_SUBMIT_RPC,
          payload: JSON.stringify({ action, values }),
          responseTimeout: 10_000,
        });
        // The agent drives whatever comes next by publishing the next phase.
        if (action === 'cancel') setUi({ phase: 'idle' });
      } catch (err) {
        console.error('Failed to submit the quote form', err);
        setBusy(false);
      }
    },
    [agent?.identity, room, values],
  );

  const body = useMemo(() => {
    switch (ui.phase) {
      case 'form':
        return (
          <QuoteForm
            fields={ui.fields ?? []}
            values={values}
            onChange={handleChange}
            onSubmit={handleSubmit}
            busy={busy}
          />
        );
      case 'loading':
        return (
          <QuoteLoading
            channels={ui.channels}
            done={progress.done}
            total={progress.total || (ui.channels ?? []).length}
            landed={landed}
          />
        );
      case 'result':
        return view === 'table' ? (
          <QuoteTable
            summary={ui.summary}
            quotes={ui.quotes ?? []}
            apiBase={API_BASE}
            onBack={() => setView('cards')}
          />
        ) : (
          <QuoteCarousel
            summary={ui.summary}
            quotes={ui.quotes ?? []}
            apiBase={API_BASE}
            onCompare={() => setView('table')}
          />
        );
      case 'error':
        return (
          <div className="quote-card quote-error">
            <h2>That didn&apos;t go through</h2>
            <p>{ui.message}</p>
          </div>
        );
      default:
        return null;
    }
  }, [ui, values, busy, view, landed, progress, handleChange, handleSubmit]);

  if (!body) return null;

  return <div className="quote-stage">{body}</div>;
}
