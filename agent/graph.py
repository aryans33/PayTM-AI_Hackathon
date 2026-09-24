"""
agent/graph.py
--------------
LangGraph StateGraph definition — wires all nodes into the dispute resolution
agent flow.

Graph topology:
                        ┌─────────────────────┐
                        │    extract_intent    │ (LLM: parse user message)
                        └──────────┬──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  decision == "clarify"?      │
                    │  (missing/malformed input)   │
                    └──────┬───────────────┬───────┘
                    YES ◄──┘               └──► NO
                    │                           │
              ┌─────▼──────┐        ┌───────────▼──────────┐
              │   respond   │        │   fetch_transaction_ │
              │ (clarify)   │        │        status        │ (SQLite)
              └─────────────┘        └───────────┬──────────┘
                                                 │
                                    ┌────────────▼────────────┐
                                    │  decision == "clarify"? │
                                    │  (transaction not found)│
                                    └──────┬──────────┬────────┘
                                    YES ◄──┘          └──► NO
                                    │                      │
                              ┌─────▼──────┐   ┌──────────▼──────────┐
                              │   respond   │   │   policy_decision   │ (pure Python)
                              │ (clarify)   │   └──────────┬──────────┘
                              └─────────────┘              │
                                          ┌────────────────┤
                                          │                │
                               ┌──────────▼─────┐   ┌─────▼────────────┐
                               │  execute_action │   │     escalate     │
                               │  (auto_resolve) │   │  (fraud/ambig/   │
                               └──────────┬──────┘   │   high-value)    │
                                          │          └──────┬───────────┘
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │     respond      │ (LLM: generate reply)
                                          └────────┬─────────┘
                                                   │
                                                  END
"""

from __future__ import annotations

import asyncio
from typing import Callable, Awaitable, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgentState
from agent.nodes.extract_intent import extract_intent
from agent.nodes.fetch_status import fetch_transaction_status
from agent.nodes.policy_decision import policy_decision
from agent.nodes.execute_action import execute_action
from agent.nodes.escalate import escalate
from agent.nodes.respond import respond

# ---------------------------------------------------------------------------
# Conditional routing helpers
# ---------------------------------------------------------------------------

def _route_after_extract(state: AgentState) -> str:
    """Route after extract_intent: clarify (missing info) or fetch transaction status."""
    if state.get("decision") == "clarify":
        return "respond"
    return "fetch_status"


def _route_after_fetch(state: AgentState) -> str:
    """Route after fetch_status: clarify (not found) or run policy."""
    if state.get("decision") == "clarify":
        return "respond"
    return "policy_decision"


def _route_after_policy(state: AgentState) -> str:
    """Route after policy_decision to the appropriate action node."""
    decision = state.get("decision")
    if decision == "auto_resolve":
        return "execute_action"
    if decision == "escalate":
        return "escalate"
    # inform_resolved, inform_pending → go straight to respond
    return "respond"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Build and compile the LangGraph StateGraph.

    Returns the compiled graph. In the FastAPI layer, the compiled graph is
    instantiated once at startup and reused for all requests (thread-safe for
    concurrent WebSocket connections via thread_id-based checkpointing).
    """
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("extract_intent",  extract_intent)
    builder.add_node("fetch_status",    fetch_transaction_status)
    builder.add_node("policy_decision", policy_decision)
    builder.add_node("execute_action",  execute_action)
    builder.add_node("escalate",        escalate)
    builder.add_node("respond",         respond)

    # Entry point
    builder.set_entry_point("extract_intent")

    # Conditional edges
    builder.add_conditional_edges("extract_intent",  _route_after_extract)
    builder.add_conditional_edges("fetch_status",    _route_after_fetch)
    builder.add_conditional_edges("policy_decision", _route_after_policy)

    # Terminal edges (always go to respond or END)
    builder.add_edge("execute_action", "respond")
    builder.add_edge("escalate",       "respond")
    builder.add_edge("respond",        END)

    # Checkpointer — MemorySaver is in-process, sufficient for a demo.
    # Production would use AsyncPostgresSaver.
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# Module-level compiled graph (singleton — built once, reused across requests)
_graph = build_graph()


# ---------------------------------------------------------------------------
# Public API — called by FastAPI WebSocket handler
# ---------------------------------------------------------------------------

async def run_agent(
    message: str,
    thread_id: str,
    trace_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> dict:
    """
    Run the dispute resolution agent for a user message.

    Parameters
    ----------
    message : str
        The raw user message.
    thread_id : str
        Unique conversation thread ID (used by MemorySaver for state persistence
        across turns). Use a UUID per user session.
    trace_callback : async callable, optional
        If provided, called with each new trace line as the agent processes.
        This enables real-time WebSocket streaming of the trace panel.
        Signature: async def callback(trace_line: str) -> None

    Returns
    -------
    dict with keys:
        response_to_user : str
        decision         : str
        trace            : list[str]
        handover_summary : str | None
    """
    initial_state: AgentState = {
        "user_message":       message,
        "transaction_id":     None,
        "transaction_status": None,
        "amount":             None,
        "complaint_type":     None,
        "payer_vpa":          None,
        "payee_vpa":          None,
        "payee_name":         None,
        "initiated_at":       None,
        "decision":           None,
        "escalation_reason":  None,
        "handover_summary":   None,
        "response_to_user":   None,
        "trace":              [],
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Use stream_mode="updates" to get per-node partial state dicts.
    # LangGraph 1.x defaults to "values" (full state snapshot per step);
    # "updates" gives {node_name: {fields_this_node_returned}} which is
    # what we need to stream trace lines as each node completes.
    seen_trace_count = 0

    async for chunk in _graph.astream(initial_state, config=config, stream_mode="updates"):
        # chunk is {node_name: partial_state_dict}
        for node_name, node_output in chunk.items():
            if node_name == "__end__":
                continue
            if not isinstance(node_output, dict):
                continue
            trace_lines: list = node_output.get("trace", [])
            if not isinstance(trace_lines, list):
                continue
            # Each node returns the FULL accumulated trace list, so new lines
            # are everything from seen_trace_count onwards.
            new_lines = trace_lines[seen_trace_count:]
            for line in new_lines:
                if trace_callback:
                    await trace_callback(line)
            seen_trace_count = len(trace_lines)

    # Retrieve the final complete state from the in-memory checkpointer.
    full_state = _graph.get_state(config).values

    return {
        "response_to_user": full_state.get("response_to_user", ""),
        "decision":         full_state.get("decision", ""),
        "trace":            full_state.get("trace", []),
        "handover_summary": full_state.get("handover_summary"),
        "transaction_id":   full_state.get("transaction_id"),
        "amount":           full_state.get("amount"),
    }


def run_agent_sync(message: str, thread_id: str) -> dict:
    """
    Synchronous wrapper around run_agent for use in test_agent.py and CLI scripts.
    Uses asyncio.run() which creates a fresh event loop — safe for repeated
    calls in a sync context (Python 3.10+ / Windows compatible).
    """
    return asyncio.run(run_agent(message, thread_id))
