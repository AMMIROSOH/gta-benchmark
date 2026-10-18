"""Agent policies; the runner owns timing, controls and task judgments."""

from importlib import import_module

# Lazy imports keep optional provider dependencies out of offline commands.
AGENTS = {"jev": ("sa_agent.agents.jev", "JevAgent")}


def create_agent(config):
    name = config["name"]
    if name not in AGENTS:
        raise ValueError(f"Unknown agent: {name}. Register it in sa_agent/agents/__init__.py.")
    module, factory = AGENTS[name]
    return getattr(import_module(module), factory)(config)
