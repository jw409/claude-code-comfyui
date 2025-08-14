<template>
  <div class="h-screen flex flex-col bg-[var(--theme-bg-secondary)]">
    <!-- Header with Primary Theme Colors -->
    <header class="bg-gradient-to-r from-[var(--theme-primary)] to-[var(--theme-primary-light)] shadow-lg border-b-2 border-[var(--theme-primary-dark)]">
      <div class="px-3 py-4 mobile:py-2 mobile:flex-col mobile:space-y-2 flex items-center justify-between">
        <!-- Title Section -->
        <div class="mobile:w-full mobile:text-center">
          <h1 class="text-2xl mobile:text-lg font-bold text-white drop-shadow-lg">
            Multi-Agent Observability
          </h1>
        </div>
        
        <!-- Connection Status -->
        <div class="mobile:w-full mobile:justify-center flex items-center space-x-1.5">
          <div v-if="isConnected" class="flex items-center space-x-1.5">
            <span class="relative flex h-3 w-3">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
            <span class="text-base mobile:text-sm text-white font-semibold drop-shadow-md">Connected</span>
          </div>
          <div v-else class="flex items-center space-x-1.5">
            <span class="relative flex h-3 w-3">
              <span class="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </span>
            <span class="text-base mobile:text-sm text-white font-semibold drop-shadow-md">Disconnected</span>
          </div>
        </div>
        
        <!-- Stream Controls & User Interface -->
        <div class="mobile:w-full mobile:justify-center flex items-center space-x-2">
          <span class="text-base mobile:text-sm text-white font-semibold drop-shadow-md bg-[var(--theme-primary-dark)] px-3 py-1.5 rounded-full border border-white/30">
            {{ events.length }} events
          </span>
          
          <!-- Stream Controls -->
          <div class="flex items-center space-x-1">
            <!-- Play/Pause Stream -->
            <button
              @click="toggleStreamPause"
              class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
              :title="streamPaused ? 'Resume stream' : 'Pause stream'"
            >
              <span class="text-lg">{{ streamPaused ? '▶️' : '⏸️' }}</span>
            </button>
            
            <!-- Clear Events -->
            <button
              @click="clearEvents"
              class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
              title="Clear all events"
            >
              <span class="text-lg">🗑️</span>
            </button>
            
            <!-- Export Events -->
            <button
              @click="exportEvents"
              class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
              title="Export events as JSON"
            >
              <span class="text-lg">💾</span>
            </button>
          </div>
          
          <!-- Connection Controls -->
          <div class="flex items-center space-x-1">
            <!-- Reconnect -->
            <button
              @click="forceReconnect"
              class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
              title="Force reconnect"
              :disabled="isConnected"
              :class="{ 'opacity-50': isConnected }"
            >
              <span class="text-lg">🔄</span>
            </button>
            
            <!-- Request Replay -->
            <button
              @click="requestEventReplay"
              class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
              title="Request event replay"
            >
              <span class="text-lg">⏮️</span>
            </button>
          </div>
          
          <!-- Filters Toggle Button -->
          <button
            @click="showFilters = !showFilters"
            class="p-3 mobile:p-1.5 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
            :title="showFilters ? 'Hide filters' : 'Show filters'"
          >
            <span class="text-2xl mobile:text-lg">📊</span>
          </button>
          
          <!-- Health Monitor -->
          <button
            @click="showHealthModal = true"
            class="p-2 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
            title="Stream health monitor"
          >
            <span class="text-lg">🏥</span>
          </button>
          
          <!-- Theme Manager Button -->
          <button
            @click="handleThemeManagerClick"
            class="p-3 mobile:p-1.5 rounded-lg bg-white/20 hover:bg-white/30 transition-all duration-200 border border-white/30 hover:border-white/50 backdrop-blur-sm shadow-lg hover:shadow-xl"
            title="Open theme manager"
          >
            <span class="text-2xl mobile:text-lg">🎨</span>
          </button>
        </div>
      </div>
    </header>
    
    <!-- Filters -->
    <FilterPanel
      v-if="showFilters"
      :filters="filters"
      @update:filters="filters = $event"
    />
    
    <!-- Live Pulse Chart -->
    <LivePulseChart
      :events="events"
      :filters="filters"
    />
    
    <!-- Timeline -->
    <EventTimeline
      :events="events"
      :filters="filters"
      v-model:stick-to-bottom="stickToBottom"
    />
    
    <!-- Stick to bottom button -->
    <StickScrollButton
      :stick-to-bottom="stickToBottom"
      @toggle="stickToBottom = !stickToBottom"
    />
    
    <!-- Error message -->
    <div
      v-if="error"
      class="fixed bottom-4 left-4 mobile:bottom-3 mobile:left-3 mobile:right-3 bg-red-100 border border-red-400 text-red-700 px-3 py-2 mobile:px-2 mobile:py-1.5 rounded mobile:text-xs"
    >
      {{ error }}
    </div>
    
    <!-- Health Monitor Modal -->
    <div v-if="showHealthModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click="showHealthModal = false">
      <div class="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto" @click.stop>
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-xl font-bold">Stream Health Monitor</h2>
          <button @click="showHealthModal = false" class="text-gray-500 hover:text-gray-700">✕</button>
        </div>
        
        <div class="space-y-4">
          <!-- Connection Status -->
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">Connection Status</h3>
            <div class="grid grid-cols-2 gap-4 text-sm">
              <div>Status: <span :class="isConnected ? 'text-green-600' : 'text-red-600'">{{ isConnected ? 'Connected' : 'Disconnected' }}</span></div>
              <div>Client ID: <span class="font-mono">{{ clientId || 'Not assigned' }}</span></div>
            </div>
          </div>
          
          <!-- Stream Statistics -->
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">Stream Statistics</h3>
            <div class="grid grid-cols-2 gap-4 text-sm">
              <div>Events: {{ events.length }}</div>
              <div>Stream: {{ streamPaused ? 'Paused' : 'Active' }}</div>
            </div>
          </div>
          
          <!-- Server Health -->
          <div class="p-4 border rounded-lg">
            <h3 class="font-semibold mb-2">Server Health</h3>
            <div v-if="serverHealth" class="space-y-2 text-sm">
              <div>Active Connections: {{ serverHealth.active_connections }}</div>
              <div>Buffered Events: {{ serverHealth.buffered_events }}</div>
              <div>Stream Status: {{ serverHealth.stream_status }}</div>
            </div>
            <div v-else class="text-gray-500">Loading...</div>
          </div>
          
          <!-- Controls -->
          <div class="flex space-x-2">
            <button @click="refreshHealth" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
              Refresh
            </button>
            <button @click="downloadHealthReport" class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
              Download Report
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Theme Manager -->
    <ThemeManager 
      :is-open="showThemeManager"
      @close="showThemeManager = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useWebSocket } from './composables/useWebSocket';
import EventTimeline from './components/EventTimeline.vue';
import FilterPanel from './components/FilterPanel.vue';
import StickScrollButton from './components/StickScrollButton.vue';
import LivePulseChart from './components/LivePulseChart.vue';
import ThemeManager from './components/ThemeManager.vue';

// WebSocket connection with controls
const { events, isConnected, error, clientId, connectionHealth, requestReplay, disconnect } = useWebSocket('ws://localhost:8889');

// Filters
const filters = ref({
  sourceApp: '',
  sessionId: '',
  eventType: ''
});

// UI state
const stickToBottom = ref(true);
const showThemeManager = ref(false);
const showFilters = ref(false);
const showHealthModal = ref(false);

// Stream control state
const streamPaused = ref(false);
const serverHealth = ref<any>(null);
const originalEvents = ref<any[]>([]);

// Computed properties - removed unused isDark

// Stream control functions
const toggleStreamPause = () => {
  streamPaused.value = !streamPaused.value;
  console.log(streamPaused.value ? 'Stream paused' : 'Stream resumed');
};

const clearEvents = () => {
  if (confirm('Clear all events? This cannot be undone.')) {
    originalEvents.value = [...events.value]; // Backup for undo
    events.value.length = 0;
    console.log('Events cleared');
  }
};

const exportEvents = () => {
  const dataStr = JSON.stringify(events.value, null, 2);
  const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
  
  const exportFileDefaultName = `claude-events-${new Date().toISOString().slice(0,19)}.json`;
  
  const linkElement = document.createElement('a');
  linkElement.setAttribute('href', dataUri);
  linkElement.setAttribute('download', exportFileDefaultName);
  linkElement.click();
  
  console.log('Events exported');
};

const forceReconnect = () => {
  console.log('Forcing reconnect...');
  disconnect();
  // Connection will automatically retry
};

const requestEventReplay = () => {
  const since = new Date(Date.now() - 300000).toISOString(); // Last 5 minutes
  requestReplay(since);
  console.log('Event replay requested');
};

const refreshHealth = async () => {
  try {
    const response = await fetch('http://localhost:8888/api/stream/health');
    serverHealth.value = await response.json();
    console.log('Health refreshed');
  } catch (err) {
    console.error('Failed to fetch health:', err);
  }
};

const downloadHealthReport = async () => {
  await refreshHealth();
  
  const report = {
    timestamp: new Date().toISOString(),
    connection: {
      status: isConnected.value ? 'Connected' : 'Disconnected',
      clientId: clientId.value,
      connectionHealth: connectionHealth.value
    },
    stream: {
      eventCount: events.value.length,
      paused: streamPaused.value,
      lastError: error.value
    },
    server: serverHealth.value
  };
  
  const dataStr = JSON.stringify(report, null, 2);
  const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
  const exportFileDefaultName = `stream-health-${new Date().toISOString().slice(0,19)}.json`;
  
  const linkElement = document.createElement('a');
  linkElement.setAttribute('href', dataUri);
  linkElement.setAttribute('download', exportFileDefaultName);
  linkElement.click();
};

// Debug handler for theme manager
const handleThemeManagerClick = () => {
  console.log('Theme manager button clicked!');
  showThemeManager.value = true;
};

// Auto-refresh health when modal opens
watch(showHealthModal, (newVal) => {
  if (newVal) {
    refreshHealth();
  }
});
</script>