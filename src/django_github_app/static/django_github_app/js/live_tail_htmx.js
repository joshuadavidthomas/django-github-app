let pageLoadTime = new Date().toISOString();
let isPaused = false;
let isConnected = false;
let eventQueue = [];
let pauseTimer = null;

const PAUSE_TIMEOUT = 5 * 60 * 1000; // 5 minutes in milliseconds

const statusEl = document.getElementById('status');
const queueInfoEl = document.getElementById('queue-info');
const pauseBtn = document.getElementById('pause-btn');
const clearBtn = document.getElementById('clear-btn');
const container = document.getElementById('events-container');
const sseContainer = document.getElementById('live-tail-sse-container');

// Create intersection observer for animations
const animationObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting && entry.target.classList.contains('new-event')) {
      // Only remove the class (trigger animation) when visible
      setTimeout(() => {
        entry.target.classList.remove('new-event');
      }, 50);
    }
  });
}, {
  root: container,
  threshold: 0.5
});

function updateStatus(status, className) {
  statusEl.textContent = status;
  statusEl.className = 'connection-status ' + className;
}

function updatePauseButton() {
  if (!isConnected) {
    pauseBtn.textContent = 'Reconnect';
    pauseBtn.disabled = false;
    queueInfoEl.textContent = '';
  } else if (isPaused) {
    pauseBtn.textContent = 'Resume';
    if (eventQueue.length > 0) {
      queueInfoEl.textContent = `${eventQueue.length} queued`;
    } else {
      queueInfoEl.textContent = '';
    }
  } else {
    pauseBtn.textContent = 'Pause';
    queueInfoEl.textContent = '';
  }
}

function startPauseTimer() {
  if (pauseTimer) {
    clearTimeout(pauseTimer);
  }

  pauseTimer = setTimeout(() => {
    // Auto-disconnect after timeout
    if (sseContainer && sseContainer.sseEventSource) {
      sseContainer.sseEventSource.close();
    }
    isConnected = false;
    isPaused = false;
    eventQueue = [];
    updateStatus('Disconnected', 'error');
    updatePauseButton();
  }, PAUSE_TIMEOUT);
}

function cancelPauseTimer() {
  if (pauseTimer) {
    clearTimeout(pauseTimer);
    pauseTimer = null;
  }
}

function drainEventQueue() {
  if (eventQueue.length === 0) return;

  const calculateDelay = () => {
    if (eventQueue.length > 50) return 20;
    if (eventQueue.length > 20) return 50;
    if (eventQueue.length > 5) return 75;
    return 100;
  };

  const drainNext = () => {
    if (eventQueue.length > 0 && !isPaused) {
      const eventHtml = eventQueue.shift();
      // Manually insert the queued HTML
      container.insertAdjacentHTML('afterbegin', eventHtml);
      const newEvent = container.firstElementChild;
      setupNewEvent(newEvent);
      updatePauseButton();

      if (eventQueue.length > 0) {
        setTimeout(drainNext, calculateDelay());
      }
    }
  };

  drainNext();
}

// Recursively sort object keys (case-insensitive) - matches admin JSON formatting
function sortObject(obj, depth = 0) {
  if (depth > 100) return obj;

  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => sortObject(item, depth + 1));
  }

  return Object.keys(obj)
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
    .reduce((sorted, key) => {
      sorted[key] = sortObject(obj[key], depth + 1);
      return sorted;
    }, {});
}

function formatJsonPayload(payloadElement) {
  if (!payloadElement) return;

  try {
    // Get the raw JSON string from the element
    const rawJson = payloadElement.textContent.trim();
    if (!rawJson) return;

    // Parse and reformat the JSON with proper indentation
    const parsed = JSON.parse(rawJson);
    const sorted = sortObject(parsed);
    const formatted = JSON.stringify(sorted, null, 2);
    
    // Update the element content with formatted JSON
    payloadElement.textContent = formatted;
  } catch (e) {
    // If parsing fails, leave the original content
    console.warn('Failed to format JSON payload:', e);
  }
}

function setupNewEvent(newEvent) {
  if (newEvent && newEvent.classList.contains('event-entry')) {
    // Format the JSON payload if it exists
    const payloadElement = newEvent.querySelector('.event-payload');
    if (payloadElement) {
      formatJsonPayload(payloadElement);
    }

    // Observe this element for visibility-based animation
    animationObserver.observe(newEvent);

    // Keep only the latest 50 events
    const events = container.querySelectorAll('.event-entry');
    if (events.length > 50) {
      for (let i = 50; i < events.length; i++) {
        animationObserver.unobserve(events[i]);
        events[i].remove();
      }
    }
  }
}

function reconnectSSE() {
  // Update the since parameter and reconnect
  if (sseContainer) {
    pageLoadTime = new Date().toISOString();
    const newUrl = `stream/?since=${pageLoadTime}`;
    
    // Close existing connection
    if (sseContainer.sseEventSource) {
      sseContainer.sseEventSource.close();
    }
    
    // Update the sse-connect attribute and reinitialize
    sseContainer.setAttribute('sse-connect', newUrl);
    htmx.process(sseContainer);
  }
}

// HTMX SSE event listeners
document.body.addEventListener('htmx:sseOpen', function(event) {
  isConnected = true;
  updateStatus('Connected', 'connected');
  updatePauseButton();
  cancelPauseTimer();
});

document.body.addEventListener('htmx:sseError', function(event) {
  isConnected = false;
  updateStatus('Connection Error - Retrying...', 'error');
  updatePauseButton();
});

document.body.addEventListener('htmx:sseClose', function(event) {
  if (isConnected) {
    isConnected = false;
    updateStatus('Connection Closed', 'error');
    updatePauseButton();
  }
});

// Override HTMX's default SSE swap behavior to handle pause logic
document.body.addEventListener('htmx:beforeSwap', function(event) {
  // Check if this is an SSE swap (no xhr means SSE)
  if (event.detail.xhr === undefined && event.detail.serverResponse) {
    if (isPaused) {
      // Don't swap, add to queue instead
      eventQueue.push(event.detail.serverResponse);
      updatePauseButton();
      event.preventDefault();
      return false;
    }
  }
});

// Handle the actual swapping and animation setup for non-paused events
document.body.addEventListener('htmx:afterSwap', function(event) {
  // Check if this is an SSE swap (no xhr means SSE)
  if (event.detail.xhr === undefined) {
    const newEvent = container.firstElementChild;
    setupNewEvent(newEvent);
  }
});

// Button event listeners
pauseBtn.addEventListener('click', function() {
  if (!isConnected) {
    eventQueue = [];
    isPaused = false;
    reconnectSSE();
    return;
  }

  if (isPaused) {
    isPaused = false;
    cancelPauseTimer();
    drainEventQueue();
    updateStatus('Connected', 'connected');
  } else {
    isPaused = true;
    startPauseTimer();
    updateStatus('Paused', '');
  }

  updatePauseButton();
});

clearBtn.addEventListener('click', function() {
  const events = container.querySelectorAll('.event-entry');
  events.forEach(event => animationObserver.unobserve(event));
  
  container.innerHTML = '';
  eventQueue = [];
  updatePauseButton();
});

// Initialize
updateStatus('Connecting...', '');

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
  if (pauseTimer) {
    clearTimeout(pauseTimer);
  }
  animationObserver.disconnect();
});