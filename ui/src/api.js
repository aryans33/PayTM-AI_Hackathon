/* ui/src/api.js
 * API helpers for the UPI Dispute Resolution AI Agent frontend.
 *
 * WebSocket protocol (server → client):
 *   { type: "trace",    content: "<line>" }  — live trace line
 *   { type: "response", content: "<text>" }  — final agent response
 *   { type: "done",     decision, transaction_id, amount, handover_summary }
 *   { type: "error",    content: "<msg>" }
 *
 * Client → server:
 *   { message: "<user text>" }
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_BASE  = API_BASE.replace(/^http/, "ws");

// ---------------------------------------------------------------------------
// REST — fetch transaction list (for demo picker)
// ---------------------------------------------------------------------------

export async function fetchTransactions() {
  const res = await fetch(`${API_BASE}/transactions`);
  if (!res.ok) throw new Error(`Failed to fetch transactions: ${res.status}`);
  const data = await res.json();
  return data.transactions;
}

// ---------------------------------------------------------------------------
// WebSocket chat session with auto-reconnect
// ---------------------------------------------------------------------------

/**
 * Open a WebSocket chat session for a given thread_id.
 * Automatically retries connection with exponential back-off if the server is
 * not yet available (e.g. page loaded before `uvicorn` started).
 *
 * @param {string} threadId   - Unique session identifier (UUID)
 * @param {object} handlers   - Event handler callbacks
 * @param {function} handlers.onTrace     - Called with each trace line string
 * @param {function} handlers.onResponse  - Called with the final response string
 * @param {function} handlers.onDone      - Called with the done metadata object
 * @param {function} handlers.onError     - Called with an error string
 * @param {function} handlers.onOpen      - Called when connection opens
 * @param {function} handlers.onClose     - Called when connection closes (before retry)
 * @param {function} handlers.onReconnect - Called when a reconnect attempt starts
 *
 * @returns {{ send: function(msg: string): void, close: function(): void }}
 */
export function createChatSession(threadId, handlers = {}) {
  let ws = null;
  let retryCount = 0;
  let destroyed = false;          // set to true when caller calls close()
  let retryTimer = null;

  const MAX_RETRIES = 12;
  const BASE_DELAY_MS = 500;      // 0.5 s → 1 s → 2 s → 4 s … max ~30 s

  function connect() {
    if (destroyed) return;

    ws = new WebSocket(`${WS_BASE}/ws/${threadId}`);

    ws.onopen = () => {
      retryCount = 0;             // reset back-off on successful connection
      handlers.onOpen?.();
    };

    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        handlers.onError?.("Received malformed JSON from server");
        return;
      }

      switch (msg.type) {
        case "trace":
          handlers.onTrace?.(msg.content);
          break;
        case "response":
          handlers.onResponse?.(msg.content);
          break;
        case "done":
          handlers.onDone?.(msg);
          break;
        case "error":
          handlers.onError?.(msg.content);
          break;
        default:
          console.warn("[ws] Unknown message type:", msg.type);
      }
    };

    ws.onerror = () => {
      // onerror always fires before onclose — do NOT add error message here.
      // The retry logic in onclose will handle recovery transparently.
      console.warn(`[ws] Connection error (attempt ${retryCount + 1})`);
    };

    ws.onclose = (event) => {
      handlers.onClose?.();

      // Do not retry if we intentionally closed or exceeded retry limit
      if (destroyed) return;
      if (retryCount >= MAX_RETRIES) {
        handlers.onError?.(
          `Could not connect to the API server after ${MAX_RETRIES} attempts. ` +
          `Make sure uvicorn is running on port 8000.`
        );
        return;
      }

      // Exponential back-off: 500ms, 1s, 2s, 4s … capped at 30s
      const delay = Math.min(BASE_DELAY_MS * Math.pow(2, retryCount), 30_000);
      retryCount++;

      if (retryCount <= 3) {
        // Silent retries for the first few — the server might just be starting
        console.info(`[ws] Reconnecting in ${delay}ms (attempt ${retryCount})…`);
      } else {
        handlers.onReconnect?.(retryCount);
      }

      retryTimer = setTimeout(connect, delay);
    };
  }

  connect();

  return {
    send: (message) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ message }));
      }
    },
    close: () => {
      destroyed = true;
      clearTimeout(retryTimer);
      ws?.close();
    },
    get isOpen() {
      return ws?.readyState === WebSocket.OPEN;
    },
  };
}
