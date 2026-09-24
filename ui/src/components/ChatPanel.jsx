/* ui/src/components/ChatPanel.jsx
 * Chat interface — Lucide icons, no emoji, light theme.
 * No logic changes from previous version.
 */
import { useState, useRef, useEffect } from "react";
import {
  Send,
  User,
  ListChecks,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Info,
  HelpCircle,
  CreditCard,
} from "lucide-react";
import { LogoMark } from "../App";

/* Demo transactions grouped by decision path — all 25 from the mock DB */
const DEMO_GROUPS = [
  {
    label: "Auto-Resolve (Rs.<=5,000, past window)",
    transactions: [
      { id: "TXN_AUTO_001", label: "TXN_AUTO_001 — Rs.300   · QuickMart · auto_resolve" },
      { id: "TXN_AUTO_002", label: "TXN_AUTO_002 — Rs.75    · Ola Cabs  · auto_resolve" },
      { id: "TXN_AUTO_003", label: "TXN_AUTO_003 — Rs.1,200 · Domino's  · auto_resolve" },
      { id: "TXN_AUTO_004", label: "TXN_AUTO_004 — Rs.4,850 · Nykaa     · auto_resolve" },
      { id: "TXN_AUTO_005", label: "TXN_AUTO_005 — Rs.499   · Hotstar   · auto_resolve" },
      { id: "TXN_AUTO_006", label: "TXN_AUTO_006 — Rs.2,750 · Lenskart  · auto_resolve" },
    ],
  },
  {
    label: "Escalate — High Value (Rs.>5,000)",
    transactions: [
      { id: "TXN_HIGH_001", label: "TXN_HIGH_001 — Rs.12,500 · AirTickets    · escalate" },
      { id: "TXN_HIGH_002", label: "TXN_HIGH_002 — Rs.28,000 · Reliance Dig  · escalate" },
      { id: "TXN_HIGH_003", label: "TXN_HIGH_003 — Rs.7,500  · Goibibo       · escalate" },
      { id: "TXN_HIGH_004", label: "TXN_HIGH_004 — Rs.55,000 · Tanishq       · escalate" },
    ],
  },
  {
    label: "Escalate — Ambiguous (conflicting records)",
    transactions: [
      { id: "TXN_AMB_001", label: "TXN_AMB_001 — Rs.2,100 · RentPay     · escalate" },
      { id: "TXN_AMB_002", label: "TXN_AMB_002 — Rs.640   · Urban Co.   · escalate" },
      { id: "TXN_AMB_003", label: "TXN_AMB_003 — Rs.9,800 · Cleartrip   · escalate" },
    ],
  },
  {
    label: "Escalate — Fraud Flagged",
    transactions: [
      { id: "TXN_FRAUD_001", label: "TXN_FRAUD_001 — Rs.4,999  · Unknown Merchant · escalate" },
      { id: "TXN_FRAUD_002", label: "TXN_FRAUD_002 — Rs.18,500 · Phishing Store   · escalate" },
      { id: "TXN_FRAUD_003", label: "TXN_FRAUD_003 — Rs.999    · Fake Recharge    · escalate" },
    ],
  },
  {
    label: "Inform Pending (within 24h reversal window)",
    transactions: [
      { id: "TXN_PEND_001", label: "TXN_PEND_001 — Rs.800   · Zomato      · inform_pending" },
      { id: "TXN_PEND_002", label: "TXN_PEND_002 — Rs.3,200 · MakeMyTrip  · inform_pending" },
      { id: "TXN_PEND_003", label: "TXN_PEND_003 — Rs.150   · BookMyShow  · inform_pending" },
      { id: "TXN_PEND_004", label: "TXN_PEND_004 — Rs.4,999 · Myntra      · inform_pending" },
    ],
  },
  {
    label: "Inform Resolved (payment succeeded)",
    transactions: [
      { id: "TXN_OK_001", label: "TXN_OK_001 — Rs.1,500 · BigBasket  · inform_resolved" },
      { id: "TXN_OK_002", label: "TXN_OK_002 — Rs.299   · Swiggy     · inform_resolved" },
      { id: "TXN_OK_003", label: "TXN_OK_003 — Rs.4,750 · IRCTC      · inform_resolved" },
      { id: "TXN_OK_004", label: "TXN_OK_004 — Rs.999   · Netflix    · inform_resolved" },
      { id: "TXN_OK_005", label: "TXN_OK_005 — Rs.249   · PharmEasy  · inform_resolved" },
    ],
  },
];

/* Decision pill config — Lucide icon + label + CSS class */
const DECISION_PILL = {
  auto_resolve:    { cls: "pill-auto-resolve",    label: "Auto-Resolved",    Icon: CheckCircle2 },
  escalate:        { cls: "pill-escalate",         label: "Escalated",        Icon: AlertTriangle },
  inform_pending:  { cls: "pill-inform-pending",   label: "Reversal Pending", Icon: Clock },
  inform_resolved: { cls: "pill-inform-resolved",  label: "Payment Success",  Icon: CheckCircle2 },
  clarify:         { cls: "pill-clarify",          label: "Needs Info",       Icon: HelpCircle },
};

/* Single message bubble */
function Message({ msg }) {
  const isUser  = msg.role === "user";
  const isError = msg.role === "error";
  const pill    = msg.decision ? DECISION_PILL[msg.decision] : null;
  const amountFmt = msg.amount
    ? `Rs.${Number(msg.amount).toLocaleString("en-IN")}`
    : null;

  if (isUser) {
    return (
      <div className="message-wrapper message-user">
        <div className="message-bubble bubble-user">{msg.content}</div>
        <div className="user-avatar" aria-label="You">
          <User size={15} strokeWidth={2} />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="message-wrapper message-error">
        <div className="agent-avatar" aria-label="System">
          <AlertTriangle size={14} strokeWidth={2} color="#fff" />
        </div>
        <div className="message-bubble bubble-error">{msg.content}</div>
      </div>
    );
  }

  return (
    <div className="message-wrapper message-agent">
      {/* Agent avatar uses the product logo mark */}
      <div className="agent-avatar" aria-label="Paytm Dispute AI">
        <LogoMark size={20} style={{ color: "#ffffff" }} />
      </div>
      <div className="message-bubble bubble-agent">
        {msg.content}
        {pill && (
          <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}>
            <span className={`message-decision-pill ${pill.cls}`}>
              <pill.Icon size={10} strokeWidth={2.5} />
              {pill.label}
            </span>
            {amountFmt && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {amountFmt}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* Typing indicator */
function TypingIndicator() {
  return (
    <div className="message-wrapper message-agent">
      <div className="agent-avatar" aria-label="Paytm Dispute AI">
        <LogoMark size={20} style={{ color: "#ffffff" }} />
      </div>
      <div className="message-bubble bubble-agent bubble-typing">
        <span className="typing-dot" />
        <span className="typing-dot" />
        <span className="typing-dot" />
      </div>
    </div>
  );
}

/* Main ChatPanel */
export default function ChatPanel({
  messages,
  onSendMessage,
  isProcessing,
  wsConnected,
  wsRetrying,
}) {
  const [inputText, setInputText]         = useState("");
  const [selectedTxnId, setSelectedTxnId] = useState("");
  const messagesEndRef = useRef(null);
  const inputRef       = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isProcessing]);

  const handlePickerChange = (e) => {
    const val = e.target.value;
    setSelectedTxnId(val);
    if (val) {
      setInputText(
        `My payment failed but money was deducted. Transaction ID: ${val}`
      );
      inputRef.current?.focus();
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const text = inputText.trim();
    if (!text || isProcessing || !wsConnected) return;
    onSendMessage(text);
    setInputText("");
    setSelectedTxnId("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const canSend = wsConnected && !isProcessing && inputText.trim().length > 0;

  return (
    <div className="chat-panel">

      {/* Sub-header */}
      <div className="chat-header">
        <div className="chat-header-title">Dispute Chat</div>
      </div>

      {/* Demo scenario picker */}
      <div className="demo-picker">
        <label className="picker-label" htmlFor="txn-picker">
          <ListChecks size={13} strokeWidth={2} />
          Quick Demo Scenarios
        </label>
        <select
          id="txn-picker"
          className="picker-select"
          value={selectedTxnId}
          onChange={handlePickerChange}
          disabled={isProcessing}
        >
          <option value="">Select a transaction to auto-fill the input</option>
          {DEMO_GROUPS.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.transactions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <p className="picker-hint">
          Or type a transaction ID directly — the agent reads natural language.
        </p>
      </div>

      {/* Messages */}
      <div className="messages-area" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="messages-empty">
            <div className="empty-icon-wrap" aria-hidden="true">
              <CreditCard size={26} strokeWidth={1.5} />
            </div>
            <h3 className="empty-title">How can I help you?</h3>
            <p className="empty-text">
              Describe your UPI payment issue or pick a demo scenario above.
              The agent checks transaction status and either resolves it
              autonomously or escalates to a human.
            </p>
            <div className="example-prompts">
              <p className="example-label">Try saying:</p>
              <button
                className="example-btn"
                onClick={() =>
                  setInputText(
                    "My Rs.300 payment to QuickMart failed, transaction ID TXN_AUTO_001"
                  )
                }
              >
                "Rs.300 payment failed — TXN_AUTO_001"
              </button>
              <button
                className="example-btn"
                onClick={() =>
                  setInputText(
                    "Flight booking payment Rs.12500 debited but not confirmed, TXN_HIGH_001"
                  )
                }
              >
                "Rs.12,500 flight booking failed — TXN_HIGH_001"
              </button>
              <button
                className="example-btn"
                onClick={() =>
                  setInputText(
                    "Suspicious charge on my account, transaction TXN_FRAUD_001"
                  )
                }
              >
                "Suspicious charge — TXN_FRAUD_001"
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}

        {isProcessing && <TypingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="input-area">
        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={inputRef}
            id="message-input"
            className="message-input"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your payment issue (Enter to send)"
            rows={2}
            disabled={isProcessing || !wsConnected}
            aria-label="Message input"
          />
          <button
            type="submit"
            id="send-btn"
            className={`send-btn${isProcessing ? " processing" : ""}`}
            disabled={!canSend}
            aria-label="Send message"
          >
            {isProcessing ? (
              <span className="btn-spinner" />
            ) : (
              <Send size={15} strokeWidth={2} />
            )}
          </button>
        </form>
        <p className="input-hint">Shift+Enter for new line · Enter to send</p>
      </div>
    </div>
  );
}
