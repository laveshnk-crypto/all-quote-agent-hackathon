import { useState, useCallback } from 'react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  BarVisualizer,
  VoiceAssistantControlBar,
  useVoiceAssistant
} from '@livekit/components-react';
import '@livekit/components-styles';

// Component to visualize agent audio output
function AgentVisualizer() {
  const { state, audioTrack } = useVoiceAssistant();
  return (
    <div style={{ height: '100px', width: '300px', margin: '0 auto' }}>
      <p style={{ textTransform: 'capitalize' }}>Status: {state}</p>
      <BarVisualizer state={state} barCount={7} trackRef={audioTrack} />
    </div>
  );
}

export default function VoiceAssistant() {
  const [token, setToken] = useState(null);
  const [url, setUrl] = useState('');
  const [connected, setConnected] = useState(false);

  const startSession = useCallback(async () => {
    if (connected) {
      setConnected(false);
      setToken(null);
      return;
    }

    try {
      // Fetch token from your FastAPI backend port (e.g. 8001)
      const res = await fetch('http://localhost:8001/api/token');
      const data = await res.json();

      setToken(data.accessToken);
      setUrl(data.url);
      setConnected(true);
    } catch (err) {
      console.error("Failed to fetch LiveKit token:", err);
    }
  }, [connected]);

  return (
    <div className="voice-assistant-container" style={{ textAlign: 'center', padding: '20px' }}>
      <button 
        onClick={startSession}
        style={{
          padding: '12px 24px',
          fontSize: '16px',
          borderRadius: '25px',
          cursor: 'pointer',
          backgroundColor: connected ? '#ff4d4d' : '#007bff',
          color: '#fff',
          border: 'none'
        }}
      >
        {connected ? 'End Voice Call' : 'Start Voice Call'}
      </button>

      {connected && token && url && (
        <LiveKitRoom
          serverUrl={url}
          token={token}
          connect={connected}
          audio={true}
          video={false}
          onDisconnected={() => {
            setConnected(false);
            setToken(null);
          }}
          style={{ marginTop: '20px' }}
        >
          {/* AudioRenderer handles playing incoming TTS audio from Cartesia */}
          <RoomAudioRenderer />
          
          {/* Shows live visualizer feedback */}
          <AgentVisualizer />

          {/* Mute/Unmute microphone controls */}
          <VoiceAssistantControlBar controls={{ leave: false }} />
        </LiveKitRoom>
      )}
    </div>
  );
}