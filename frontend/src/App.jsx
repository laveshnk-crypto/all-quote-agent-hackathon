import { useState, useCallback } from 'react';
import { LiveKitRoom, RoomAudioRenderer } from '@livekit/components-react';
import '@livekit/components-styles';

import './App.css';
import lucideBot from './assets/lucide--bot.svg';
import QuoteExperience from './components/QuoteExperience.jsx';

// Split so the two halves can carry different colour, and every letter gets its
// own index for the staggered entrance and the shimmer that follows it.
const BRAND = [
  ['Omni', 'accent'],
  ['Quote', 'light'],
];

export default function App() {
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
      const res = await fetch('http://localhost:8001/api/token');
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

        <button
          className={`logo-circle ${connected ? 'active' : ''}`}
          type="button"
          aria-label="LucidBot"
          onClick={handleToggleConnection}
        >
          <img className="bot-logo" src={lucideBot} alt="LucidBot" />
        </button>
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