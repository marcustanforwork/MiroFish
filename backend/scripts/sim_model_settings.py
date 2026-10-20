"""
Request settings for the simulation agents' model, read from the environment.

LLM_SIM_REASONING_EFFORT  e.g. "none": no thinking on agent turns
LLM_SIM_CACHE_CONTROL     "ephemeral" (5-minute cache) or "ephemeral:1h": asks
                          OpenRouter to cache the prompt, which Anthropic models
                          only do when a request says so. An agent's memory only
                          grows at the end, so each turn re-reads the last one's
                          prompt from cache.

camel passes model_config_dict straight to the OpenAI client, so cache_control
travels in extra_body. Never put max_tokens here: camel reads it as the agent's
whole context window (BaseModelBackend.token_limit), not as a cap on the reply.
"""

from typing import Any, Dict, Mapping, Optional

_CACHE_OFF = {"", "off", "none", "false", "0"}


def sim_model_config(environ: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    config: Dict[str, Any] = {}

    reasoning_effort = (environ.get("LLM_SIM_REASONING_EFFORT") or "").strip()
    if reasoning_effort:
        config["reasoning_effort"] = reasoning_effort

    cache = (environ.get("LLM_SIM_CACHE_CONTROL") or "").strip().lower()
    if cache not in _CACHE_OFF:
        cache_type, _, ttl = cache.partition(":")
        cache_control = {"type": cache_type}
        if ttl:
            cache_control["ttl"] = ttl
        config["extra_body"] = {"cache_control": cache_control}

    return config or None
