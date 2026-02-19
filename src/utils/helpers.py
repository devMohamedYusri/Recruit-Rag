import time
import logging

logger = logging.getLogger(__name__)


async def track_llm_call(
    generation_client,
    prompt: str,
    config: dict,
    usage_controller=None,
    project_id: str = None,
    file_id: str = None,
    action_type: str = "generation"
):
    """
    Wraps an LLM generate() call with latency measurement and usage logging.

    Returns:
        LLMResponse — the raw response from the generation client.
    """
    start_time = time.perf_counter()
    response = await generation_client.generate(prompt=prompt, config=config)
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    if usage_controller and project_id and response.usage_metadata:
        await usage_controller.log_usage(
            project_id=project_id,
            model_id=generation_client.model_id,
            action_type=action_type,
            usage_metadata=response.usage_metadata,
            file_id=file_id,
            latency_ms=latency_ms
        )

    return response
