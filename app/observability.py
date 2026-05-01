"""Langfuse v3 observability.

@observe creates parent trace spans. LLM calls log themselves as nested
generations under the active span — see app.llm.client.LlmClient.

We intentionally do NOT use `litellm.success_callback = ["langfuse"]`:
its classic integration was built against the Langfuse v2 SDK and breaks on
v3 (e.g. unexpected `sdk_integration` kwarg). Manual logging via the v3
client gives us a single, properly nested trace tree.

Initialization is driven by env vars: LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, LANGFUSE_HOST. If unset, the client becomes a no-op.
"""

from langfuse import get_client, observe  # noqa: F401  re-exports

__all__ = ["observe", "get_client"]
