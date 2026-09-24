/* ui/src/App.jsx — Root layout + global top nav. No logic changes. */
import { useState, useEffect, useRef, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import ChatPanel  from "./components/ChatPanel";
import TracePanel from "./components/TracePanel";
import { createChatSession } from "./api";
import "./App.css";

/**
 * LogoMark — clean SVG monogram for "Paytm Dispute AI".
 * A shield with a stylised checkmark/spark. Scales via width/height props.
 */
export function LogoMark({ size = 28, style, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {/* Shield body */}
      <path
        d="M16 2L4 7v8c0 7.18 5.16 13.9 12 15.93C22.84 28.9 28 22.18 28 15V7L16 2z"
        fill="currentColor"
        fillOpacity="0.18"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      {/* Bold bolt */}
      <path
        d="M18.5 9l-7 9.5h5.5l-1.5 5.5 7-9.5H17l1.5-5.5z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function App() {
  const [messages, setMessages]         = useState([]);
  const [traceLines, setTraceLines]     = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [wsConnected, setWsConnected]   = useState(false);
  const [wsRetrying, setWsRetrying]     = useState(false);
  const [decision, setDecision]         = useState(null);

  const threadIdRef = useRef(sessionStorage.getItem("upi_thread_id") || uuidv4());
  const sessionRef  = useRef(null);

  useEffect(() => {
    const tid = threadIdRef.current;
    sessionStorage.setItem("upi_thread_id", tid);

    sessionRef.current = createChatSession(tid, {
      onOpen:      () => { setWsConnected(true);  setWsRetrying(false); },
      onClose:     () => { setWsConnected(false); },
      onReconnect: () => { setWsRetrying(true); },

      onTrace: (line) => setTraceLines((prev) => [...prev, line]),

      onResponse: (content) =>
        setMessages((prev) => [...prev, { role: "agent", content }]),

      onDone: (meta) => {
        setDecision(meta.decision);
        setIsProcessing(false);
        if (meta.handover_summary) {
          setMessages((prev) => [...prev, {
            role:     "agent",
            content:  "Handover summary sent to human support agent.",
            decision: meta.decision,
            amount:   meta.amount,
          }]);
        } else {
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = [...updated].reverse().findIndex((m) => m.role === "agent");
            if (lastIdx !== -1) {
              const idx = updated.length - 1 - lastIdx;
              updated[idx] = { ...updated[idx], decision: meta.decision, amount: meta.amount };
            }
            return updated;
          });
        }
      },

      onError: (msg) => {
        setIsProcessing(false);
        setMessages((prev) => [...prev, { role: "error", content: msg }]);
      },
    });

    return () => sessionRef.current?.close();
  }, []);

  const handleSendMessage = useCallback((text) => {
    if (!wsConnected || isProcessing) return;
    setMessages((prev)  => [...prev, { role: "user", content: text }]);
    setTraceLines([]);
    setDecision(null);
    setIsProcessing(true);
    sessionRef.current?.send(text);
  }, [wsConnected, isProcessing]);

  const wsState = wsConnected ? "connected" : wsRetrying ? "reconnecting" : "disconnected";
  const wsLabel = wsConnected ? "Connected"  : wsRetrying ? "Reconnecting" : "Connecting";

  return (
    <div id="app-root" className="app-root">

      {/* Global top navigation bar */}
      <header className="top-nav" role="banner">
        <div className="top-nav-left">
          <div className="top-nav-logo">
            <LogoMark size={28} style={{ color: "#ffffff" }} />
          </div>
          <span className="top-nav-name">Paytm Dispute AI</span>
          <span className="top-nav-badge">Hackathon Demo</span>
        </div>
        <div className="top-nav-right">
          <div className={`nav-ws-status ${wsState}`} title={`WebSocket: ${wsLabel}`}>
            <span className="nav-ws-dot" />
            {wsLabel}
          </div>
        </div>
      </header>

      {/* Reconnect banner — only after several silent retries */}
      {wsRetrying && (
        <div className="reconnect-banner" role="alert">
          <span className="reconnect-spinner" />
          Reconnecting — run{" "}
          <code>uvicorn api.main:app --reload --port 8000</code>
        </div>
      )}

      {/* Two-panel layout */}
      <div className="app-panels">
        <ChatPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          isProcessing={isProcessing}
          wsConnected={wsConnected}
          wsRetrying={wsRetrying}
        />
        <div className="panel-divider" aria-hidden="true" />
        <TracePanel
          traceLines={traceLines}
          isProcessing={isProcessing}
          decision={decision}
        />
      </div>
    </div>
  );
}
