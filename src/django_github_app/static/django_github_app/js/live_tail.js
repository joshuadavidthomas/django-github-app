let eventSource = null;
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
  root: container, // Observe within the scroll container
  threshold: 0.5   // Trigger when 50% visible
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
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    isConnected = false;
    isPaused = false;
    eventQueue = []; // Clear queue on disconnect
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
    // Speed up based on queue size
    if (eventQueue.length > 50) return 20;  // Very fast for large backlogs
    if (eventQueue.length > 20) return 50;  // Fast
    if (eventQueue.length > 5) return 75;   // Medium
    return 100; // Normal speed for small queues
  };

  const drainNext = () => {
    if (eventQueue.length > 0 && !isPaused) {
      const eventData = eventQueue.shift();
      addEventToDOM(eventData);
      updatePauseButton();

      // Continue draining with adaptive delay
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

function formatEvent(eventData) {
  const timestamp = new Date(eventData.received_at).toLocaleString();
  const eventType = eventData.event || 'unknown';
  const action = eventData.action ? ':' + eventData.action : '';

  // Sort the payload keys to match admin interface formatting
  let payload = '';
  if (eventData.payload) {
    try {
      const sortedPayload = sortObject(eventData.payload);
      payload = JSON.stringify(sortedPayload, null, 2);
    } catch (e) {
      payload = JSON.stringify(eventData.payload, null, 2);
    }
  }

  return `
        <div class="event-entry">
            <div class="event-meta">
                [${timestamp}] ID: ${eventData.id}
            </div>
            <div>
                <span class="event-type">${eventType}</span><span class="event-action">${action}</span>
            </div>
            ${payload ? `<div class="event-payload">${payload}</div>` : ''}
        </div>
    `;
}

function addEventToDOM(eventData) {
  if (!eventData.id) return;

  const eventHtml = formatEvent(eventData);
  container.insertAdjacentHTML('afterbegin', eventHtml);

  // Get the newly added element and add animation class
  const newEvent = container.firstElementChild;
  newEvent.classList.add('new-event');

  // Observe this element for visibility-based animation
  animationObserver.observe(newEvent);

  // Keep only the latest 50 events
  const events = container.querySelectorAll('.event-entry');
  if (events.length > 50) {
    for (let i = 50; i < events.length; i++) {
      // Clean up observer for removed elements
      animationObserver.unobserve(events[i]);
      events[i].remove();
    }
  }
}

function addEvent(eventData) {
  if (!eventData.id) return;

  if (isPaused) {
    // Queue the event instead of displaying it
    eventQueue.push(eventData);
    updatePauseButton();
    return;
  }

  addEventToDOM(eventData);
}

function startSSE() {
  if (eventSource) {
    eventSource.close();
  }

  updateStatus('Connecting...', '');

  const streamUrl = new URL('stream/', window.location.href);
  streamUrl.searchParams.set('since', pageLoadTime);

  eventSource = new EventSource(streamUrl.toString());

  eventSource.onopen = function () {
    isConnected = true;
    updateStatus('Connected', 'connected');
    updatePauseButton();
  };

  eventSource.onmessage = function (event) {
    try {
      const eventData = JSON.parse(event.data);
      if (eventData.id) {
        addEvent(eventData); // addEvent handles pausing internally now
      }
    } catch (e) {
      console.error('Error parsing event data:', e);
    }
  };

  eventSource.onerror = function () {
    isConnected = false;
    updateStatus('Connection Error - Retrying...', 'error');
    updatePauseButton();
    setTimeout(() => {
      if (!isPaused) {
        startPolling();
      }
    }, 3000);
  };
}

function startPolling() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  isConnected = true;
  updateStatus('Polling...', 'connected');
  updatePauseButton();

  const poll = () => {
    if (isPaused) {
      setTimeout(poll, 2000);
      return;
    }

    const streamUrl = new URL('stream/', window.location.href);
    streamUrl.searchParams.set('since', pageLoadTime);

    fetch(streamUrl.toString())
      .then(response => {
        if (!response.ok) throw new Error('Network error');
        return response.text();
      })
      .then(text => {
        const lines = text.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.substring(6));
              if (eventData.id) {
                addEvent(eventData); // addEvent handles pausing internally
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
        setTimeout(poll, 2000);
      })
      .catch(() => {
        isConnected = false;
        updateStatus('Polling Error - Retrying...', 'error');
        updatePauseButton();
        setTimeout(poll, 5000);
      });
  };

  setTimeout(poll, 1000);
}

// Event listeners
pauseBtn.addEventListener('click', function () {
  if (!isConnected) {
    // Reconnect
    eventQueue = [];
    isPaused = false;
    pageLoadTime = new Date().toISOString(); // Reset to current time
    if (typeof EventSource !== 'undefined') {
      startSSE();
    } else {
      startPolling();
    }
    return;
  }

  if (isPaused) {
    // Resume: drain queue and continue
    isPaused = false;
    cancelPauseTimer();
    drainEventQueue();
    updateStatus('Connected', 'connected');
  } else {
    // Pause: start queuing events
    isPaused = true;
    startPauseTimer();
    updateStatus('Paused', '');
  }

  updatePauseButton();
});

clearBtn.addEventListener('click', function () {
  // Clean up all observers before clearing
  const events = container.querySelectorAll('.event-entry');
  events.forEach(event => animationObserver.unobserve(event));

  container.innerHTML = '';
  // Also clear the queue if paused
  eventQueue = [];
  updatePauseButton();
});

// Start with SSE, fallback to polling
if (typeof EventSource !== 'undefined') {
  startSSE();
} else {
  startPolling();
}

// Cleanup on page unload
window.addEventListener('beforeunload', function () {
  if (eventSource) {
    eventSource.close();
  }
  if (pauseTimer) {
    clearTimeout(pauseTimer);
  }
  // Clean up intersection observer
  animationObserver.disconnect();
});
