"""
common/observability.py — Arize/OpenTelemetry tracing, structurally incapable of
breaking run_pipeline(). This module is standalone and touches none of the 6 already-
shipped agent files; it's the fail-safe primitive everything else will be built on top
of, built and proven FIRST per the design checkpoint.

THE ONE RULE EVERYTHING HERE SERVES: a broken Arize connection, invalid credentials, or
a failing quality-judge call must never change run_pipeline()'s real return value or
raise an exception the rest of the pipeline wasn't already prepared to handle. Structurally
enforced, not just documented, by `traced_span`'s own shape (see its docstring) — the
ONLY line that ever executes the caller's real business code (`yield span`) is completely
outside any try/except in this module. Everything ELSE (span creation, attribute-setting,
teardown) is wrapped, because those are the only places telemetry infrastructure code
runs. This is the opposite failure mode of "swallow everything" — swallowing a REAL
business exception would hide an actual bug behind broken observability, which is just as
unacceptable as observability breaking the pipeline outright.

Credentials: ARIZE_SPACE_ID / ARIZE_API_KEY via env vars, same pattern as every other
credential in this project (see CLAUDE.md's coding conventions).
"""
import logging
import os
from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger("singleslide.observability")

_tracer: Optional[Any] = None
_enabled = False

T = TypeVar("T")


def init_tracing(project_name: str = "singleslide", debug: bool = False) -> bool:
    """Attempts to initialize Arize/OpenTelemetry tracing. NEVER raises — returns False
    (and logs a warning) on ANY failure (missing credentials, register() itself throwing,
    a missing dependency), leaving tracing fully disabled for the rest of the process.
    Call once, at run_pipeline()'s start.

    Real, verified finding: arize.otel.register() does NOT validate credentials against
    the network at call time — it succeeds locally even with fake space_id/api_key,
    deferring all real network activity to a background export thread (which
    OpenTelemetry's own BatchSpanProcessor already isolates from caller control flow).
    So this function's own try/except mostly guards against local failures (a missing
    dependency, a malformed argument) — the network/auth failure modes the caller asked
    about are handled one layer down, in the actual quality-judge call wrapper
    (safe_eval_call), which makes real synchronous Anthropic API calls in the
    pipeline's own control flow and genuinely can fail there.
    """
    global _tracer, _enabled
    space_id = os.environ.get("ARIZE_SPACE_ID")
    api_key = os.environ.get("ARIZE_API_KEY")
    if not space_id or not api_key:
        if debug:
            print("[observability debug] ARIZE_SPACE_ID/ARIZE_API_KEY not set — tracing disabled.\n")
        _enabled = False
        return False

    try:
        from arize.otel import register
        from opentelemetry import trace as otel_trace

        register(space_id=space_id, api_key=api_key, project_name=project_name, verbose=debug)
        _tracer = otel_trace.get_tracer("singleslide")
        _enabled = True
        if debug:
            print(f"[observability debug] tracing initialized for project '{project_name}'\n")
        return True
    except Exception as err:  # noqa: BLE001 — this layer is fully best-effort, by design
        logger.warning(f"Observability initialization failed, continuing without tracing: {err}")
        _tracer = None
        _enabled = False
        return False


class _NullSpan:
    """Span-shaped no-op — every method does nothing and cannot raise. Used both when
    tracing was never initialized and as the fallback if a real span's own creation
    fails."""

    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        pass

    def set_attributes(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        pass


class _SafeSpan:
    """Wraps a real OTel span so every method call-site code makes is individually
    fail-safe — call-site code (e.g. an agent setting llm.token_count after a real API
    call returns) never needs its own try/except around a span attribute call."""

    def __init__(self, real_span: Any):
        self._real = real_span

    def set_attribute(self, key: str, value: Any) -> None:
        try:
            self._real.set_attribute(key, value)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"observability: set_attribute({key!r}) failed, continuing: {err}")

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        try:
            self._real.set_attributes(attributes)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"observability: set_attributes failed, continuing: {err}")

    def record_exception(self, exc: BaseException) -> None:
        try:
            self._real.record_exception(exc)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"observability: record_exception failed, continuing: {err}")


@contextmanager
def traced_span(name: str, kind: str, attributes: Optional[dict[str, Any]] = None):
    """The one place every call site creates a span. Structurally incapable of breaking
    the wrapped code: span setup (before `yield`) and teardown (in `finally`) are the
    ONLY telemetry infrastructure code here, and both are fully wrapped in try/except —
    on any failure (tracing disabled, span creation fails, an attribute-setting call
    fails), the caller gets a safe no-op span and its own code runs completely
    unaffected.

    Deliberately NOT wrapped: the `yield span` line itself. Whatever the caller's real
    business code does inside `with traced_span(...) as span:` — including raising a
    genuine exception — happens with zero interference from this function. Swallowing a
    real business exception would hide an actual bug behind broken observability, which
    this module treats as equally unacceptable as observability breaking the pipeline.
    """
    span_cm = None
    span: Any = _NullSpan()

    if _enabled and _tracer is not None:
        try:
            from openinference.semconv.trace import SpanAttributes

            span_cm = _tracer.start_as_current_span(name)
            real_span = span_cm.__enter__()
            span = _SafeSpan(real_span)
            span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, kind)
            if attributes:
                span.set_attributes(attributes)
        except Exception as err:  # noqa: BLE001
            logger.debug(f"observability: span setup for '{name}' failed, continuing without tracing: {err}")
            span_cm = None
            span = _NullSpan()

    try:
        yield span
    finally:
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception as err:  # noqa: BLE001
                logger.debug(f"observability: span teardown for '{name}' failed: {err}")


async def safe_eval_call(coro_factory: Callable[[], Awaitable[T]], *, judge_name: str, debug: bool = False) -> Optional[T]:
    """The one place every LLM-judge quality-scoring call runs. A judge call is a real,
    synchronous Anthropic API call in the pipeline's own control flow — genuinely capable
    of failing (timeout, auth error, malformed response) in a way span setup/teardown
    above cannot. Wrapped the same way: any failure returns None (never raises), and the
    caller treats a None score as "not scored this run," never as a fabricated 0 or a
    reason to fail the real pipeline.

    coro_factory is a zero-arg callable returning the awaitable (not the awaitable
    itself) so this function fully controls when the call starts — the failure must be
    caught from inside this function's own try/except, not before it.
    """
    try:
        return await coro_factory()
    except Exception as err:  # noqa: BLE001
        logger.warning(f"Quality-judge call '{judge_name}' failed, continuing without a score: {err}")
        if debug:
            print(f"[observability debug] safe_eval_call('{judge_name}') failed: {err}\n")
        return None


def llm_span_attributes(
    model_name: str,
    usage: Optional[dict[str, Any]],
    invocation_parameters: dict[str, Any],
    input_value: str,
    output_value: str,
    total_cost_usd: Optional[float] = None,
) -> dict[str, Any]:
    """Builds the standard attribute dict for an LLM-kind span from a claude_agent_sdk
    ResultMessage's real fields. usage is passed straight through from
    ResultMessage.usage (a raw, SDK-untyped `dict[str, Any] | None` — see
    docs/DECISION_LOG.md for why cache-token keys are read defensively here rather than
    assumed present).

    Every attribute-builder in this module (this one included) is called UNCONDITIONALLY
    at every call site, often as an argument evaluated before traced_span() is even
    entered (e.g. `traced_span(name, kind, obs.input_value_attribute(prompt))`) — so it
    cannot rely on traced_span's own try/except for protection; it must never raise on its
    own. Returns {} (no attributes set, not a crash) on any failure, most realistically an
    openinference package that isn't installed.
    """
    try:
        import json as _json

        from openinference.semconv.trace import SpanAttributes

        attrs: dict[str, Any] = {
            SpanAttributes.LLM_MODEL_NAME: model_name,
            SpanAttributes.LLM_SYSTEM: "anthropic",
            SpanAttributes.LLM_INVOCATION_PARAMETERS: _json.dumps(invocation_parameters),
            SpanAttributes.INPUT_VALUE: input_value,
            SpanAttributes.OUTPUT_VALUE: output_value,
        }
        if total_cost_usd is not None:
            attrs[SpanAttributes.LLM_COST_TOTAL] = total_cost_usd

        usage = usage or {}
        prompt_tokens = usage.get("input_tokens")
        completion_tokens = usage.get("output_tokens")
        if prompt_tokens is not None:
            attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] = prompt_tokens
        if completion_tokens is not None:
            attrs[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = completion_tokens
        if prompt_tokens is not None and completion_tokens is not None:
            attrs[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] = prompt_tokens + completion_tokens

        # Real Anthropic prompt-cache fields, per the standard Messages API usage shape —
        # NOT hard-confirmed against a live ResultMessage.usage dict from THIS SDK (it's
        # typed dict[str, Any] and passed through unmodified from the CLI subprocess's raw
        # JSON — see claude_agent_sdk's own message_parser.py). Read defensively: only set
        # if actually present, never fabricated as 0 when absent.
        cache_read = usage.get("cache_read_input_tokens")
        cache_write = usage.get("cache_creation_input_tokens")
        if cache_read is not None:
            attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] = cache_read
        if cache_write is not None:
            attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_WRITE] = cache_write

        return attrs
    except Exception as err:  # noqa: BLE001
        logger.debug(f"observability: llm_span_attributes failed, returning no attributes: {err}")
        return {}


def tool_span_attributes(tool_name: str, tool_description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        import json as _json

        from openinference.semconv.trace import SpanAttributes

        return {
            SpanAttributes.TOOL_NAME: tool_name,
            SpanAttributes.TOOL_DESCRIPTION: tool_description,
            SpanAttributes.TOOL_PARAMETERS: _json.dumps(parameters),
        }
    except Exception as err:  # noqa: BLE001
        logger.debug(f"observability: tool_span_attributes failed, returning no attributes: {err}")
        return {}


def input_value_attribute(value: str) -> dict[str, Any]:
    """Small helper so call sites can set input.value at span-creation time (before an
    agentic call starts, so a mid-call crash still leaves a trace with real input
    visible) without needing their own top-level `openinference.semconv` import — every
    agent file already imports observability lazily; this keeps that true for its
    attribute-building helpers too, not just traced_span/safe_eval_call themselves."""
    try:
        from openinference.semconv.trace import SpanAttributes

        return {SpanAttributes.INPUT_VALUE: value}
    except Exception as err:  # noqa: BLE001
        logger.debug(f"observability: input_value_attribute failed, returning no attributes: {err}")
        return {}


def output_value_attribute(value: Any) -> dict[str, Any]:
    """Same reasoning as input_value_attribute, for the one caller (common/mcp_client.py's
    call()) that only knows its output AFTER the wrapped call returns, so it can't be
    folded into a single llm_span_attributes()-style builder call the way agentic call
    sites do."""
    try:
        from openinference.semconv.trace import SpanAttributes

        return {SpanAttributes.OUTPUT_VALUE: str(value)}
    except Exception as err:  # noqa: BLE001
        logger.debug(f"observability: output_value_attribute failed, returning no attributes: {err}")
        return {}


def evaluation_attributes(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Real, verified mechanism (openinference.instrumentation.get_evaluation_attributes)
    — distinct from regular span attributes, per its own spec area
    (EvaluationAttributes/SpanAttributes.EVALUATIONS in openinference-semconv). Attaches
    directly onto the SAME span as the LLM call it's judging, via span.set_attributes(),
    not a separate API call or a child span — confirmed by reading the real
    openinference-instrumentation package source, not assumed.

    Takes a LIST of evaluations, not a single one: get_evaluation_attributes flattens by
    list INDEX (evaluations.0.*, evaluations.1.*, ...). Discovered while wiring Part C's
    dual groundedness+coherence judge — calling this twice with one entry each would have
    silently collided, both producing evaluations.0.* and the second call's
    span.set_attributes() overwriting the first's scores rather than adding a second
    entry. Each dict: {"name": str, "score": float|None, "label": str|None,
    "explanation": str|None, "annotator_kind": str} — annotator_kind defaults to "LLM"
    if omitted.
    """
    try:
        from openinference.instrumentation import get_evaluation_attributes

        normalized = [{"annotator_kind": "LLM", **e} for e in evaluations]
        return dict(get_evaluation_attributes(evaluations=normalized, scope="span"))
    except Exception as err:  # noqa: BLE001
        logger.debug(f"observability: evaluation_attributes failed, returning no attributes: {err}")
        return {}
