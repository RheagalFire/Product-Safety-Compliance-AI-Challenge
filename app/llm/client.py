from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from app.observability import get_client

T = TypeVar("T", bound=BaseModel)


class LlmClient:
    """Thin litellm wrapper. Every call manually opens a Langfuse v3
    generation span via `start_as_current_generation`, so the LLM call
    nests under whichever @observe-decorated function is on the stack."""

    async def structured(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        lf = get_client()
        with lf.start_as_current_generation(
            name="llm.structured",
            model=model,
            input=messages,
        ) as gen:
            resp = await litellm.acompletion(
                model=model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                        "strict": True,
                    },
                },
                **kwargs,
            )
            content = resp.choices[0].message.content
            obj = schema.model_validate_json(content)

            update: dict[str, Any] = {"output": content}
            usage = getattr(resp, "usage", None)
            if usage is not None:
                update["usage_details"] = {
                    "input": getattr(usage, "prompt_tokens", None),
                    "output": getattr(usage, "completion_tokens", None),
                    "total": getattr(usage, "total_tokens", None),
                }
            gen.update(**update)
            return obj
