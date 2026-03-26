"""Simple stateful agent with Neo4j checkpointer.

Demonstrates LangGraph + Neo4j checkpoint persistence across invocations.
No LLM needed — uses a fake "echo" model and a simple tool.

Run as script:
    NEO4J_PASSWORD=<your_password> uv run python examples/simple_agent.py

Or execute cell-by-cell in Zed / Jupyter / VS Code (look for # %% markers).

Requires a running Neo4j instance on bolt://localhost:7387 by default
(to match the current docker-compose host port mapping), unless `NEO4J_URI`
is set explicitly.
"""

# %% [1] Imports

from __future__ import annotations

import asyncio
import os
import re
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from langgraph.checkpoint.neo4j import Neo4jSaver
from langgraph.checkpoint.neo4j.aio import AsyncNeo4jSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

# %% [2] Configuration — edit these or set env vars

NEO4J_HOST = os.environ.get("NEO4J_HOST", "localhost")
NEO4J_BOLT_PORT = os.environ.get("NEO4J_BOLT_PORT", "7387")
NEO4J_HTTP_PORT = os.environ.get("NEO4J_HTTP_PORT", "7373")
NEO4J_URI = os.environ.get("NEO4J_URI", f"bolt://{NEO4J_HOST}:{NEO4J_BOLT_PORT}")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

THREAD_ID = "demo-thread-1"

print(f"Neo4j Host:       {NEO4J_HOST}")
print(f"Neo4j Bolt Port:  {NEO4J_BOLT_PORT}")
print(f"Neo4j HTTP Port:  {NEO4J_HTTP_PORT}")
print(f"Neo4j URI:        {NEO4J_URI}")
print(f"Neo4j User:       {NEO4J_USER}")
print(f"Thread ID:        {THREAD_ID}")

# %% [3] Define graph state + nodes

_MATH_RE = re.compile(r"(\d+(?:\.\d+)?\s*[+\-*/]\s*\d+(?:\.\d+)?)")


class AgentState(TypedDict):
    """Simple agent state: a list of messages + a turn counter."""

    messages: Annotated[list[BaseMessage], add_messages]
    turn_count: int


def chatbot_node(state: AgentState) -> dict[str, Any]:
    """Fake chatbot: echoes input, routes math expressions to calculator."""
    messages = state["messages"]
    last_message = messages[-1]
    turn_count = state.get("turn_count", 0) + 1
    user_text = last_message.content if isinstance(last_message, HumanMessage) else ""

    math_match = _MATH_RE.search(user_text)
    if math_match:
        expression = math_match.group(1).strip()
        return {
            "messages": [
                AIMessage(
                    content=f"Let me calculate: {expression}",
                    additional_kwargs={"calc_expression": expression},
                )
            ],
            "turn_count": turn_count,
        }

    return {
        "messages": [AIMessage(content=f"[Turn {turn_count}] You said: {user_text}")],
        "turn_count": turn_count,
    }


def calculator_node(state: AgentState) -> dict[str, Any]:
    """Evaluate the math expression from the last AI message."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage):
        expression = last_message.additional_kwargs.get("calc_expression")
        if expression and re.fullmatch(r"[\d\s+\-*/.()]+", expression):
            result = eval(expression)
            return {
                "messages": [AIMessage(content=f"Calculator: {expression} = {result}")]
            }
    return {"messages": []}


def should_calculate(state: AgentState) -> str:
    """Conditional edge: route to calculator if AI wants to calculate."""
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, AIMessage) and last.additional_kwargs.get("calc_expression"):
        return "calculator"
    return "end"


print("Graph nodes defined.")

# %% [4] Build graph helper


def build_graph(checkpointer: Neo4jSaver | AsyncNeo4jSaver) -> Any:
    """Build a simple stateful graph with conditional branching."""
    builder = StateGraph(AgentState)
    builder.add_node("chatbot", chatbot_node)
    builder.add_node("calculator", calculator_node)
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges(
        "chatbot",
        should_calculate,
        {"calculator": "calculator", "end": END},
    )
    builder.add_edge("calculator", END)
    return builder.compile(checkpointer=checkpointer)


print("build_graph() ready.")

# %% [5] SYNC DEMO — create checkpointer, setup schema, run conversations

print("\n" + "=" * 60)
print("  SYNC DEMO: Neo4jSaver")
print("=" * 60 + "\n")

with Neo4jSaver.from_conn_string(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as saver:
    saver.setup()
    print("Schema setup complete (idempotent).\n")

    graph = build_graph(saver)
    config = {"configurable": {"thread_id": THREAD_ID}}

    # --- Check for pre-existing state ---
    existing = saver.get_tuple(config)
    if existing:
        cv = existing.checkpoint.get("channel_values", {})
        print(
            f"Resuming! turn_count={cv.get('turn_count', 0)}, messages={len(cv.get('messages', []))}"
        )
    else:
        print("No existing state — starting fresh.\n")

    # --- Send messages ---
    for user_input in [
        "Hello, Neo4j checkpointer!",
        "What is 42 + 17?",
        "Remember me across restarts!",
    ]:
        print(f">>> User: {user_input}")
        result = graph.invoke({"messages": [HumanMessage(content=user_input)]}, config)
        print(f"<<< Agent: {result['messages'][-1].content}")
        print(f"    (turn_count={result.get('turn_count', '?')})\n")

    # --- Inspect ---
    final = saver.get_tuple(config)
    if final:
        print(f"Final checkpoint: {final.config['configurable']['checkpoint_id']}")
        print(
            f"Total messages in state: {len(final.checkpoint.get('channel_values', {}).get('messages', []))}"
        )

    # --- Cleanup ---
    saver.delete_thread(THREAD_ID)
    print(f"\nThread '{THREAD_ID}' deleted.")

print("\nSync demo complete.\n")

# %% [6] ASYNC DEMO — same thing, but async

print("=" * 60)
print("  ASYNC DEMO: AsyncNeo4jSaver")
print("=" * 60 + "\n")


async def async_demo() -> None:
    async with AsyncNeo4jSaver.from_conn_string(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    ) as saver:
        await saver.setup()
        print("Async schema setup complete.\n")

        graph = build_graph(saver)
        config = {"configurable": {"thread_id": f"{THREAD_ID}-async"}}

        for user_input in [
            "Async hello!",
            "Compute 100 * 3.14",
            "Persistence works async too!",
        ]:
            print(f">>> User: {user_input}")
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_input)]}, config
            )
            print(f"<<< Agent: {result['messages'][-1].content}")
            print(f"    (turn_count={result.get('turn_count', '?')})\n")

        # List checkpoints
        checkpoints = [cp async for cp in saver.alist(config)]
        print(f"Total checkpoints: {len(checkpoints)}")
        for idx, cp_tuple in enumerate(checkpoints[:5]):
            cid = cp_tuple.config["configurable"]["checkpoint_id"][:16]
            step = cp_tuple.metadata.get("step", "?")
            print(f"  [{idx}] id={cid}...  step={step}")

        # Cleanup
        await saver.adelete_thread(f"{THREAD_ID}-async")
        print(f"\nThread '{THREAD_ID}-async' deleted.")


asyncio.run(async_demo())
print("\nAsync demo complete.\n")

# %% [7] PERSISTENCE PROOF — write in one session, read in another

print("=" * 60)
print("  PERSISTENCE PROOF: write → close → re-open → read")
print("=" * 60 + "\n")

proof_thread = "persistence-proof"

# Write phase
with Neo4jSaver.from_conn_string(
    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
) as writer:
    writer.setup()
    graph = build_graph(writer)
    proof_config = {"configurable": {"thread_id": proof_thread}}

    writer.delete_thread(proof_thread)  # ensure clean start

    graph.invoke(
        {"messages": [HumanMessage(content="Message 1: saved to Neo4j")]}, proof_config
    )
    graph.invoke(
        {"messages": [HumanMessage(content="Message 2: still here?")]}, proof_config
    )
    print("Wrote 2 messages. Closing connection.\n")

# Read phase — completely new driver + saver
with Neo4jSaver.from_conn_string(
    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
) as reader:
    reader.setup()
    proof_config = {"configurable": {"thread_id": proof_thread}}

    restored = reader.get_tuple(proof_config)
    if restored:
        messages = restored.checkpoint.get("channel_values", {}).get("messages", [])
        print(f"Restored {len(messages)} messages from Neo4j:")
        for msg in messages:
            role = type(msg).__name__
            print(f"  [{role}] {msg.content}")
    else:
        print("ERROR: No state found! Persistence is broken.")

    # Checkpoint history
    all_checkpoints = list(reader.list(proof_config))
    print(f"\nCheckpoint history: {len(all_checkpoints)} entries")

    # Time travel — read the state after just the first message
    if len(all_checkpoints) >= 2:
        early = all_checkpoints[
            -2
        ]  # second checkpoint (after first invoke's loop step)
        early_id = early.config["configurable"]["checkpoint_id"]
        early_state = reader.get_tuple(
            {"configurable": {"thread_id": proof_thread, "checkpoint_id": early_id}}
        )
        if early_state:
            early_msgs = early_state.checkpoint.get("channel_values", {}).get(
                "messages", []
            )
            print(f"\nTime travel to checkpoint {early_id[:16]}...:")
            print(f"  Messages at that point: {len(early_msgs)}")
            for msg in early_msgs:
                print(f"    [{type(msg).__name__}] {msg.content}")

    # Cleanup
    reader.delete_thread(proof_thread)
    print(f"\nThread '{proof_thread}' deleted. Proof complete.")

print("\n" + "=" * 60)
print("  All demos complete!")
print("=" * 60)
