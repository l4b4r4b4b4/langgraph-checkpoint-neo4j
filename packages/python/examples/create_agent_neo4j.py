"""Latest-API example: `langchain.agents.create_agent` with Neo4j persistence.

This example uses LangChain v1's `create_agent` API with this package's
`Neo4jSaver` checkpointer to demonstrate real thread-level persistence.

It is designed for:
1. Quick local smoke-testing of the package
2. Verifying persistence with a real model provider
3. Testing editor/runtime integrations via executable Python cells

Supported providers:
- OpenAI (`OPENAI_API_KEY`)
- Anthropic (`ANTHROPIC_API_KEY`)

If both are present, OpenAI is preferred by default.

Run:
    NEO4J_PASSWORD=<your_password> uv run python examples/create_agent_neo4j.py

Optional:
    OPENAI_BASE_URL=https://api.openai.com/v1
    OPENAI_API_KEY=...
    OPENAI_MODEL=gpt-4.1-mini

    For a local OpenAI-compatible backend such as vLLM:
    OPENAI_BASE_URL=http://localhost:7374/v1
    OPENAI_API_KEY=dummy
    OPENAI_MODEL=ministral-3b-instruct

    ANTHROPIC_API_KEY=...
    ANTHROPIC_MODEL=claude-sonnet-4-5

Environment:
    NEO4J_HOST=localhost
    NEO4J_BOLT_PORT=7387
    NEO4J_HTTP_PORT=7373
    NEO4J_URI=bolt://localhost:7387
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password
    THREAD_ID=create-agent-demo
"""

# %% [1] Imports

from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from langgraph.checkpoint.neo4j import Neo4jSaver

# %% [2] Configuration

NEO4J_HOST = os.environ.get("NEO4J_HOST", "localhost")
NEO4J_BOLT_PORT = os.environ.get("NEO4J_BOLT_PORT", "7387")
NEO4J_HTTP_PORT = os.environ.get("NEO4J_HTTP_PORT", "7373")
NEO4J_URI = os.environ.get("NEO4J_URI", f"bolt://{NEO4J_HOST}:{NEO4J_BOLT_PORT}")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
THREAD_ID = os.environ.get("THREAD_ID", "create-agent-demo")

OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


# %% [3] Provider selection


def select_model() -> str:
    """Select the available provider/model from environment variables.

    Returns:
        A model identifier string understood by `create_agent`.

    Raises:
        RuntimeError: If no supported provider API key is configured.
    """
    if OPENAI_API_KEY:
        model_name = f"openai:{OPENAI_MODEL}"
        print(f"Using provider: OpenAI-compatible backend ({model_name})")
        print(f"OpenAI base URL: {OPENAI_BASE_URL}")
        return model_name

    if ANTHROPIC_API_KEY:
        model_name = f"anthropic:{ANTHROPIC_MODEL}"
        print(f"Using provider: Anthropic ({model_name})")
        return model_name

    raise RuntimeError(
        "No model provider configured.\n"
        "Set one of:\n"
        "  - OPENAI_API_KEY\n"
        "  - ANTHROPIC_API_KEY\n\n"
        "Examples:\n"
        "  export OPENAI_API_KEY=...\n"
        "  export OPENAI_MODEL=gpt-4.1-mini\n\n"
        "or:\n"
        "  export ANTHROPIC_API_KEY=...\n"
        "  export ANTHROPIC_MODEL=claude-sonnet-4-5"
    )


# %% [4] Define tools


@tool
def add_numbers(left: float, right: float) -> str:
    """Add two numbers and return a human-readable result.

    Args:
        left: The first number.
        right: The second number.

    Returns:
        A string containing the sum.
    """
    result = left + right
    return f"{left} + {right} = {result}"


@tool
def remember_fact(fact: str) -> str:
    """Echo back a fact so the agent can keep it in thread memory.

    This tool does not store anything external by itself. The purpose is to
    make the interaction more explicit while the actual persistence comes from
    the Neo4j checkpointer.

    Args:
        fact: The fact to remember.

    Returns:
        Confirmation text.
    """
    return f"I will remember this in the thread state: {fact}"


@tool
def current_runtime_info() -> str:
    """Return a tiny bit of runtime context useful for smoke-testing tools.

    Returns:
        A short string identifying the demo thread.
    """
    return f"Runtime thread_id={THREAD_ID}"


TOOLS = [add_numbers, remember_fact, current_runtime_info]


# %% [5] Agent factory


def build_agent(checkpointer: Neo4jSaver, model: str) -> Any:
    """Create a latest-API LangChain v1 agent with Neo4j persistence.

    Args:
        checkpointer: The Neo4j checkpointer to use for persistence.
        model: Model identifier string for `create_agent`.

    Returns:
        A compiled agent graph.
    """
    return create_agent(
        model=model,
        tools=TOOLS,
        system_prompt=(
            "You are a concise helpful assistant. "
            "Use tools when they help. "
            "If the user asks about something mentioned earlier in the same thread, "
            "use the conversation history available to you."
        ),
        checkpointer=checkpointer,
    )


# %% [6] Helpers for readable output


def _extract_last_assistant_message(messages: list[BaseMessage]) -> str:
    """Get the last assistant message content from a message list."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
    return "<no AIMessage found>"


def invoke_and_print(
    agent: Any, user_text: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Invoke the agent and print a concise summary.

    Args:
        agent: Compiled agent from `create_agent`.
        user_text: User prompt text.
        config: Runnable config containing `thread_id`.

    Returns:
        The raw agent result dict.
    """
    print(f">>> User: {user_text}")
    result = agent.invoke(
        {"messages": [HumanMessage(content=user_text)]},
        config,
    )
    messages = result.get("messages", [])
    print(f"<<< Agent: {_extract_last_assistant_message(messages)}")
    print(f"    Message count in returned state: {len(messages)}")
    print()
    return result


def print_state_summary(agent: Any, config: dict[str, Any]) -> None:
    """Print latest persisted thread state using the high-level graph API."""
    snapshot = agent.get_state(config)
    print("--- Latest persisted state ---")
    print(f"Checkpoint ID: {snapshot.config['configurable']['checkpoint_id']}")
    print(f"Next nodes:    {snapshot.next}")
    print(f"Metadata:      {snapshot.metadata}")
    values = snapshot.values
    messages = values.get("messages", [])
    print(f"Messages:      {len(messages)}")
    if messages:
        print("Last 3 messages:")
        for message in messages[-3:]:
            role = type(message).__name__
            content = getattr(message, "content", "")
            print(f"  [{role}] {content}")
    print()


def print_history_summary(agent: Any, config: dict[str, Any]) -> None:
    """Print checkpoint history using the high-level graph API."""
    history = list(agent.get_state_history(config))
    print("--- Checkpoint history ---")
    print(f"Total checkpoints: {len(history)}")
    for index, snapshot in enumerate(history[:5]):
        checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
        source = snapshot.metadata.get("source", "?")
        step = snapshot.metadata.get("step", "?")
        print(f"  [{index}] id={checkpoint_id[:16]}... source={source} step={step}")
    print()


# %% [7] Main demo — latest API + persistence


def main() -> None:
    """Run a local end-to-end persistence demo using `create_agent`."""
    print(f"Neo4j Host:       {NEO4J_HOST}")
    print(f"Neo4j Bolt Port:  {NEO4J_BOLT_PORT}")
    print(f"Neo4j HTTP Port:  {NEO4J_HTTP_PORT}")
    print(f"Neo4j URI:        {NEO4J_URI}")
    print(f"Neo4j User:       {NEO4J_USER}")
    print(f"Thread ID:        {THREAD_ID}")
    print("\n" + "=" * 72)
    print("  create_agent + Neo4jSaver persistence demo")
    print("=" * 72 + "\n")

    model = select_model()
    os.environ["OPENAI_BASE_URL"] = OPENAI_BASE_URL
    print(f"Registered tools: {[tool_.name for tool_ in TOOLS]}")
    print()

    with Neo4jSaver.from_conn_string(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    ) as checkpointer:
        # Idempotent schema setup
        checkpointer.setup()
        print("Schema setup complete.")

        # Start clean for demo repeatability
        checkpointer.delete_thread(THREAD_ID)
        print(f"Cleared old thread state for '{THREAD_ID}'.")
        print()

        agent = build_agent(checkpointer, model)
        config = {"configurable": {"thread_id": THREAD_ID}}

        # First interaction: teach the thread something
        invoke_and_print(
            agent,
            (
                "Please remember that my favorite database is Neo4j. "
                "Use the remember_fact tool if helpful."
            ),
            config,
        )

        # Second interaction: use a tool
        invoke_and_print(
            agent,
            "What is 42 + 17? Use a tool.",
            config,
        )

        # Third interaction: verify thread memory
        invoke_and_print(
            agent,
            "What did I say my favorite database is earlier in this thread?",
            config,
        )

        print_state_summary(agent, config)
        print_history_summary(agent, config)

        # Persistence proof: create a fresh agent instance on same thread
        print("--- Persistence proof via fresh agent instance ---")
        second_agent = build_agent(checkpointer, model)
        second_result = second_agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "In one short sentence, remind me what my favorite database is."
                        )
                    )
                ]
            },
            config,
        )
        restored_message = _extract_last_assistant_message(
            second_result.get("messages", [])
        )
        print(f"Restored answer: {restored_message}")
        print()

        # Optional cleanup
        print("--- Cleanup ---")
        checkpointer.delete_thread(THREAD_ID)
        print(f"Deleted thread '{THREAD_ID}'.")
        print()

    print("=" * 72)
    print("  Demo complete")
    print("=" * 72)


# %% [8] Entry point

if __name__ == "__main__":
    main()
