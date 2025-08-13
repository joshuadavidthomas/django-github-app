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
    const sseSource = htmx.find('[hx-ext="sse"]');
    if (sseSource && sseSource.sseEventSource) {
      sseSource.sseEventSource.close();
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
      addEventToDOM(eventHtml);
      updatePauseButton();

      if (eventQueue.length > 0) {
        setTimeout(drainNext, calculateDelay());
      }
    }
  };

  drainNext();
}

function addEventToDOM(eventHtml) {
  container.insertAdjacentHTML('afterbegin', eventHtml);

  const newEvent = container.firstElementChild;
  if (newEvent && newEvent.classList.contains('event-entry')) {
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

function addEvent(eventHtml) {
  if (isPaused) {
    eventQueue.push(eventHtml);
    updatePauseButton();
    return;
  }

  addEventToDOM(eventHtml);
}

function reconnectSSE() {
  // Update the since parameter and reconnect
  const container = htmx.find('[hx-ext="sse"]');
  if (container) {
    pageLoadTime = new Date().toISOString();
    const newUrl = `stream/?since=${pageLoadTime}`;
    
    // Close existing connection
    if (container.sseEventSource) {
      container.sseEventSource.close();
    }
    
    // Update the sse-connect attribute and reinitialize
    container.setAttribute('sse-connect', newUrl);
    htmx.process(container);
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

// Custom event handler for SSE messages
document.body.addEventListener('htmx:sseMessage', function(event) {
  if (event.detail.type === 'event' && event.detail.data.trim()) {
    addEvent(event.detail.data);
  }
});

// Override HTMX's default SSE swap behavior to handle our pause logic
document.body.addEventListener('htmx:beforeSwap', function(event) {
  if (event.detail.xhr === undefined && event.detail.serverResponse) {
    // This is an SSE event
    if (isPaused) {
      // Don't swap, add to queue instead
      eventQueue.push(event.detail.serverResponse);
      updatePauseButton();
      event.preventDefault();
      return false;
    }
  }
});

// Handle the actual swapping and animation setup
document.body.addEventListener('htmx:afterSwap', function(event) {
  if (event.detail.xhr === undefined) {
    // This is an SSE swap, set up animation observer
    const newEvent = container.firstElementChild;
    if (newEvent && newEvent.classList.contains('event-entry')) {
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