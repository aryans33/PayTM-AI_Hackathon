/* ui/src/components/TracePanel.jsx
 * Live decision-trace viewer — Lucide icons, light theme, terse log lines.
 * No logic changes from previous version.
 */
import { useEffect, useRef } from "react";
import {
  ScanSearch,
  Database,
  GitBranch,
  Zap,
  ArrowUpRight,
  MessageCircle,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Info,
  HelpCircle,
} from "lucide-react";

/* Node metadata — Lucide icon component + color var per node */
const NODE_META = {
  "[extract_intent]": {
    color: "var(--node-extract-color)",
    Icon:  ScanSearch,
    label: "extract_intent",
  },
  "[fetch_status]": {
    color: "var(--node-fetch-color)",
    Icon:  Database,
    label: "fetch_status",
  },
  "[policy_decision]": {
    color: "var(--node-policy-color)",
    Icon:  GitBranch,
    label: "policy_decision",
  },
  "[execute_action]": {
    color: "var(--node-execute-color)",
    Icon:  Zap,
    label: "execute_action",
  },
  "[escalate]": {
    color: "var(--node-escalate-color)",
    Icon:  ArrowUpRight,
    label: "escalate",
  },
  "[respond]": {
    color: "var(--node-respond-color)",
    Icon:  MessageCircle,
    label: "respond",
  },
};

const DEFAULT_META = {
  color: "var(--text-muted)",
  Icon:  Activity,
  label: "",
};

function getNodeMeta(line) {
  for (const [key, meta] of Object.entries(NODE_META)) {
    if (line.includes(key)) return meta;
  }
  return DEFAULT_META;
}

/* Decision summary card config — Lucide icon, label, CSS class */
const DECISION_SUMMARY = {
  auto_resolve: {
    cls:    "ds-auto-resolve",
    Icon:   CheckCircle2,
    value:  "Auto-Resolved",
    reason: "Refund initiated automatically. No human intervention required.",
  },
  escalate: {
    cls:    "ds-escalate",
    Icon:   AlertTriangle,
    value:  "Escalated to Human",
    reason: "Case handed over to a human support agent for manual review.",
  },
  inform_pending: {
    cls:    "ds-inform-pending",
    Icon:   Clock,
    value:  "Reversal Pending",
    reason: "NPCI auto-reversal in progress. Funds credited within 24-48 hours.",
  },
  inform_resolved: {
    cls:    "ds-inform-resolved",
    Icon:   Info,
    value:  "Payment Successful",
    reason: "Transaction completed successfully. No dispute action needed.",
  },
  clarify: {
    cls:    "ds-clarify",
    Icon:   HelpCircle,
    value:  "Needs Clarification",
    reason: "Transaction ID required to look up and resolve the dispute.",
  },
};

function isSeparatorLine(line) {
  // Skip lines whose content (after the node prefix) is only dashes, box-drawing
  // chars, or whitespace -- these are visual separators not meaningful log entries.
  const content = line.replace(/^\[[\w_]+\]\s*/, "").trim();
  return content === "" || /^[-─━=\s]+$/.test(content);
}

function TraceLine({ line, isNew }) {
  const meta    = getNodeMeta(line);
  const display = line.replace(/^\[[\w_]+\]\s*/, "");
  const prefix  = line.match(/^\[([\w_]+)\]/)?.[0] || "";
  const { Icon } = meta;

  return (
    <div
      className={`trace-line${isNew ? " trace-line-enter" : ""}`}
      style={{ borderLeftColor: meta.color }}
    >
      <div className="trace-icon-wrap">
        <Icon size={13} strokeWidth={2} color={meta.color} />
      </div>
      <div className="trace-content">
        {prefix && (
          <span className="trace-node-label" style={{ color: meta.color }}>
            {prefix}
          </span>
        )}
        <span className="trace-text">{display || line}</span>
      </div>
    </div>
  );
}

/* Main TracePanel */
export default function TracePanel({ traceLines, isProcessing, decision }) {
  const bottomRef  = useRef(null);
  const prevLenRef = useRef(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [traceLines, isProcessing]);

  const newLineStart = prevLenRef.current;
  useEffect(() => {
    prevLenRef.current = traceLines.length;
  }, [traceLines]);

  const summary = decision ? DECISION_SUMMARY[decision] : null;

  return (
    <div className="trace-panel">

      {/* Header */}
      <div className="trace-header">
        <div className="trace-header-left">
          <div className="trace-header-icon" aria-hidden="true">
            <Activity size={15} strokeWidth={2} />
          </div>
          <div>
            <h2 className="trace-title">Decision Trace</h2>
            <p className="trace-subtitle">Live audit log — streamed in real time</p>
          </div>
        </div>
        <div className="trace-header-right">
          {isProcessing && (
            <div className="live-badge" aria-label="Processing live">
              <span className="live-dot" />
              Live
            </div>
          )}
          {summary && !isProcessing && (
            <div
              className={`decision-badge ${summary.cls}`}
              role="status"
              aria-label={`Decision: ${summary.value}`}
            >
              <summary.Icon size={10} strokeWidth={2.5} />
              {summary.value}
            </div>
          )}
        </div>
      </div>

      {/* Node color legend */}
      <div className="trace-legend" aria-label="Node color legend">
        {Object.entries(NODE_META).map(([key, meta]) => {
          const { Icon } = meta;
          return (
            <span
              key={key}
              className="legend-item"
              style={{ color: meta.color }}
            >
              <Icon size={11} strokeWidth={2} />
              {meta.label}
            </span>
          );
        })}
      </div>

      {/* Trace lines */}
      <div className="trace-body" role="log" aria-live="polite" aria-label="Agent trace">
        {traceLines.length === 0 && !isProcessing && (
          <div className="trace-empty">
            <div className="trace-empty-icon" aria-hidden="true">
              <Activity size={24} strokeWidth={1.5} />
            </div>
            <p className="trace-empty-title">Waiting for a dispute query</p>
            <p className="trace-empty-sub">
              When you submit a message, the agent's reasoning steps appear
              here in real time.
            </p>
          </div>
        )}

        {traceLines.filter((l) => !isSeparatorLine(l)).map((line, i) => (
          <TraceLine key={i} line={line} isNew={i >= newLineStart} />
        ))}

        {isProcessing && (
          <div className="trace-thinking" aria-label="Processing">
            <span className="thinking-dot" />
            <span className="thinking-dot" />
            <span className="thinking-dot" />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Decision summary card — prominent, unmissable */}
      {summary && !isProcessing && (
        <div
          className={`decision-summary ${summary.cls}`}
          role="status"
          aria-label={`Final decision: ${summary.value}`}
        >
          <div className="decision-summary-inner">
            <div className="decision-summary-icon">
              <summary.Icon size={30} strokeWidth={1.5} />
            </div>
            <div className="decision-summary-text">
              <div className="decision-summary-label">Final Decision</div>
              <div className="decision-summary-value">{summary.value}</div>
              <div className="decision-summary-reason">{summary.reason}</div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      {traceLines.length > 0 && (
        <div className="trace-footer">
          {traceLines.length} event{traceLines.length !== 1 ? "s" : ""} · DPDP-compliant audit log
        </div>
      )}
    </div>
  );
}
