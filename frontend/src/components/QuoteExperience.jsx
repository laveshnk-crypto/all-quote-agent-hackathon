import { useCallback, useEffect, useMemo, useState } from 'react';
import { useDataChannel, useRoomContext, useVoiceAssistant } from '@livekit/components-react';

import QuoteCarousel from './QuoteCarousel.jsx';
import QuoteTable from './QuoteTable.jsx';
import './QuoteExperience.css';

const QUOTE_UI_TOPIC = 'quote.ui';
const QUOTE_SUBMIT_RPC = 'quote.submit';
// Screenshots are served by the FastAPI backend, not the Vite dev server.
const API_BASE = 'http://localhost:8001';

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

function QuoteLoading({ channels = [] }) {
  // Channels run in parallel, so rather than fake a sequence we light each one
  // up in turn to show the fan-out is live.
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((value) => value + 1), 900);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="quote-card quote-loading">
      <div className="quote-loading__orb" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <h2>Checking {channels.length || 'all'} sources</h2>
      <p className="quote-loading__step">Querying every source at once…</p>

      {channels.length > 0 && (
        <ul className="quote-loading__channels">
          {channels.map((name, index) => (
            <li key={name} className={index === tick % channels.length ? 'is-active' : ''}>
              {name}
            </li>
          ))}
        </ul>
      )}

      <div className="quote-loading__track" aria-hidden="true">
        <div className="quote-loading__bar" />
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

  useDataChannel(QUOTE_UI_TOPIC, (msg) => {
    let payload;
    try {
      payload = JSON.parse(new TextDecoder().decode(msg.payload));
    } catch (err) {
      console.error('Unreadable quote UI message', err);
      return;
    }

    setUi(payload);
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
        return <QuoteLoading channels={ui.channels} />;
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
  }, [ui, values, busy, view, handleChange, handleSubmit]);

  if (!body) return null;

  return <div className="quote-stage">{body}</div>;
}
