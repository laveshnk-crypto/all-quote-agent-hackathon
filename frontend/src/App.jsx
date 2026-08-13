import { useState, useCallback } from 'react';
import { LiveKitRoom, RoomAudioRenderer } from '@livekit/components-react';
import '@livekit/components-styles';

import './App.css';
import lucideBot from './assets/lucide--bot.svg';
import QuoteExperience from './components/QuoteExperience.jsx';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001';

// Split so the two halves can carry different colour, and every letter gets its
// own index for the staggered entrance and the shimmer that follows it.
const BRAND = [
  ['Omni', 'accent'],
  ['Quote', 'light'],
];

function Brand() {
  return (
    <h1 className="brand" aria-label="OmniQuote">
      {BRAND.map(([text, tone], wordIndex) => (
        <span className={`brand__word brand__word--${tone}`} key={text}>
          {[...text].map((char, i) => (
            <span
              className="brand__char"
              key={`${text}-${i}`}
              style={{ '--i': wordIndex * 4 + i }}
              aria-hidden="true"
            >
              {char}
            </span>
          ))}
        </span>
      ))}
    </h1>
  );
}

export default function App() {
  // Landing first: title and description, then a single call to action that
  // reveals the agent. Keeps the first screen calm instead of opening on an
  // unexplained button.
  const [entered, setEntered] = useState(false);
  const [token, setToken] = useState(null);
  const [url, setUrl] = useState('');
  const [connected, setConnected] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);

  const resetVoiceSession = useCallback(() => {
    setConnected(false);
    setToken(null);
    setUrl('');
    setSessionKey((value) => value + 1);
  }, []);

  const handleToggleConnection = useCallback(async () => {
    if (connected) {
      resetVoiceSession();
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/token`);
      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const data = await res.json();
      setToken(data.accessToken);
      setUrl(data.url);
      setConnected(true);
    } catch (err) {
      console.error('Failed to connect to LiveKit voice agent:', err);
      resetVoiceSession();
    }
  }, [connected, resetVoiceSession]);

  return (
    <>
      <div className="App">
        <div className="base"></div>

        {!entered ? (
          <main className="landing">
            <Brand />
            <p className="landing__tagline">
              Your AI insurance agent for Ontario auto quotes. Have a short
              conversation, confirm your details on screen once, and OmniQuote
              checks twelve rate sources at the same time — every figure backed
              by a screenshot of the page it came from.
            </p>
            <button
              type="button"
              className="landing__cta"
              onClick={() => setEntered(true)}
            >
              Talk to OmniQuote
            </button>
            <p className="landing__hint">
              Voice call · about two minutes · no email or phone number needed
            </p>
          </main>
        ) : (
          <div className="stage">
            <Brand />
            <button
              className={`logo-circle ${connected ? 'active' : ''}`}
              type="button"
              aria-label={connected ? 'End the call' : 'Start talking to OmniQuote'}
              onClick={handleToggleConnection}
            >
              <img className="bot-logo" src={lucideBot} alt="" />
            </button>
            <p className="stage__hint">
              {connected ? 'On a call — press the bot to hang up' : 'Press the bot to start the call'}
            </p>
          </div>
        )}
      </div>

      {token && url && (
        <LiveKitRoom
          key={sessionKey}
          serverUrl={url}
          token={token}
          connect={connected}
          audio={true}
          video={false}
          onDisconnected={resetVoiceSession}
        >
          <RoomAudioRenderer />
          <QuoteExperience />
        </LiveKitRoom>
      )}
    </>
  );
}