import { ref, onMounted, onUnmounted } from 'vue';
import type { HookEvent, WebSocketMessage } from '../types';

export function useWebSocket(url: string) {
  const events = ref<HookEvent[]>([]);
  const isConnected = ref(false);
  const error = ref<string | null>(null);
  const clientId = ref<string | null>(null);
  const connectionHealth = ref<any>({});
  
  let ws: WebSocket | null = null;
  let reconnectTimeout: number | null = null;
  let heartbeatTimeout: number | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 10;
  
  // Get max events from environment variable or use default
  const maxEvents = parseInt(import.meta.env.VITE_MAX_EVENTS_TO_DISPLAY || '100');
  
  const connect = () => {
    try {
      ws = new WebSocket(url);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
        isConnected.value = true;
        error.value = null;
        reconnectAttempts = 0; // Reset on successful connection
        resetHeartbeatTimeout();
      };
      
      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          if (message.type === 'initial') {
            const initialEvents = Array.isArray(message.data) ? message.data : [];
            events.value = initialEvents.slice(-maxEvents);
            console.log(`Loaded ${initialEvents.length} initial events`);
            
          } else if (message.type === 'event') {
            const newEvent = message.data as HookEvent;
            events.value.push(newEvent);
            
            if (events.value.length > maxEvents) {
              events.value = events.value.slice(events.value.length - maxEvents + 10);
            }
            
          } else if (message.type === 'connection') {
            clientId.value = message.data.client_id;
            connectionHealth.value = message.data;
            console.log(`Connected as client ${clientId.value}`);
            
          } else if (message.type === 'ping') {
            // Respond to heartbeat ping
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: 'pong',
                timestamp: new Date().toISOString()
              }));
            }
            
          } else if (message.type === 'replay') {
            // Handle event replay
            const replayEvents = Array.isArray(message.data) ? message.data : [];
            console.log(`Received ${replayEvents.length} replay events`);
            // Could merge with existing events or handle separately
            
          } else if (message.type === 'auth_success') {
            console.log('Authentication successful');
            
          } else if (message.type === 'auth_error') {
            console.error('Authentication failed:', message.data.message);
          }
          
          // Reset heartbeat timeout on any message
          resetHeartbeatTimeout();
          
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };
      
      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        error.value = 'WebSocket connection error';
      };
      
      ws.onclose = () => {
        console.log('WebSocket disconnected');
        isConnected.value = false;
        clearHeartbeatTimeout();
        
        // Exponential backoff reconnection
        if (reconnectAttempts < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
          console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);
          
          reconnectTimeout = window.setTimeout(() => {
            reconnectAttempts++;
            connect();
          }, delay);
        } else {
          error.value = 'Max reconnection attempts reached';
          console.error('Max reconnection attempts reached');
        }
      };
    } catch (err) {
      console.error('Failed to connect:', err);
      error.value = 'Failed to connect to server';
    }
  };
  
  const resetHeartbeatTimeout = () => {
    clearHeartbeatTimeout();
    // Set timeout to detect missing heartbeats (server sends every 30s, we timeout after 60s)
    heartbeatTimeout = window.setTimeout(() => {
      console.warn('Heartbeat timeout - connection may be stale');
      error.value = 'Connection timeout';
      // Could trigger reconnection here
    }, 60000);
  };
  
  const clearHeartbeatTimeout = () => {
    if (heartbeatTimeout) {
      clearTimeout(heartbeatTimeout);
      heartbeatTimeout = null;
    }
  };

  const disconnect = () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    
    clearHeartbeatTimeout();
    
    if (ws) {
      ws.close();
      ws = null;
    }
  };
  
  const requestReplay = (since?: string) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'replay_request',
        since: since || new Date(Date.now() - 300000).toISOString() // Last 5 minutes
      }));
    }
  };
  
  onMounted(() => {
    connect();
  });
  
  onUnmounted(() => {
    disconnect();
  });
  
  return {
    events,
    isConnected,
    error,
    clientId,
    connectionHealth,
    requestReplay,
    disconnect
  };
}