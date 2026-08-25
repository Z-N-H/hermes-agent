"""Template: register an external agent with Agno AgentOS.

Copy and run, or import and extend.
"""

import sys
from typing import Any

# CUSTOMIZE: import your adapter class here.
from agent_context.hermes_agent import HermesAgent


agent = HermesAgent(
    name="Hermes Coder",
    description="Hermes CLI exposed as an Agno external agent.",
    max_turns=10,
)


def standalone_demo() -> None:
    """Run one prompt through the agent and print streamed events."""
    prompt = "Summarize the purpose of this repository in two sentences."
    print(f"Prompt: {prompt}\n")
    for event in agent.run(prompt, stream=True):  # type: ignore[arg-type]
        print(f"[{event.event}] {getattr(event, 'content', '')}")


def serve() -> Any:
    """Register with AgentOS and boot the FastAPI app."""
    try:
        from agno.os import AgentOS
    except ImportError as e:
        print(
            "AgentOS requires the web stack: pip install 'agno[os]' "
            f"(missing: {e.name if hasattr(e, 'name') else e})",
            file=sys.stderr,
        )
        sys.exit(1)

    app = AgentOS(agents=[agent])
    print("AgentOS app created with agents:", [a.name for a in [agent]])
    print("Route: POST /agents/{id}/runs  ->  guest subprocess (SSE stream)")
    return app


def main() -> None:
    if "--serve" in sys.argv:
        serve()
    else:
        standalone_demo()


if __name__ == "__main__":
    main()
