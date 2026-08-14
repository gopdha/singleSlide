#!/usr/bin/env python3
"""
The centerpiece tier: mechanically proves observability is structurally incapable of
breaking real pipeline code — a broken Arize connection, a failing span creation, a
failing attribute-set, and a failing quality-judge call all leave a wrapped function's
real return value untouched. Also proves the opposite failure mode doesn't exist either:
a GENUINE business exception raised inside a traced_span block still propagates normally,
even when tracing itself is completely broken — this module must never swallow a real
bug behind broken telemetry.

No credentials needed for any of this — every failure mode is forced deterministically
by monkeypatching, matching this project's "verify mechanically-checkable claims in code"
convention (docs/DECISION_LOG.md) applied to the observability layer's own core promise.

Run with:
    python3 test_observability.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import observability as obs  # noqa: E402


def run_init_tracing_tests():
    print("init_tracing — fail-safe unit tests (no credentials, no network):")

    original_env = {k: os.environ.pop(k, None) for k in ("ARIZE_SPACE_ID", "ARIZE_API_KEY")}
    try:
        result = obs.init_tracing("test-project")
        assert result is False
        assert obs._enabled is False
        print("  PASS  no ARIZE_SPACE_ID/ARIZE_API_KEY set: returns False, no exception, tracing stays disabled")
    finally:
        for k, v in original_env.items():
            if v is not None:
                os.environ[k] = v

    os.environ["ARIZE_SPACE_ID"] = "fake-space"
    os.environ["ARIZE_API_KEY"] = "fake-key"
    try:
        import arize.otel

        real_register = arize.otel.register

        def _broken_register(*args, **kwargs):
            raise ConnectionError("simulated: Arize unreachable")

        arize.otel.register = _broken_register
        try:
            result = obs.init_tracing("test-project")
            assert result is False
            assert obs._enabled is False
            print("  PASS  register() itself raising (simulated unreachable/auth failure): "
                  "returns False, no exception propagates")
        finally:
            arize.otel.register = real_register
    finally:
        del os.environ["ARIZE_SPACE_ID"]
        del os.environ["ARIZE_API_KEY"]


def run_traced_span_never_breaks_wrapped_code_tests():
    print("\ntraced_span — the centerpiece: a broken Arize layer never changes the "
          "wrapped code's real return value:")

    def _do_real_work(x: int) -> int:
        """Stand-in for a real pipeline function — e.g. investigate_feature() returning
        a real FEATURE_SCHEMA dict. What matters is that ITS return value is what the
        test asserts on, completely independent of tracing's health."""
        with obs.traced_span("do_real_work", "LLM") as span:
            span.set_attribute("some.attribute", "some value")
            return x * 2

    # 1. Tracing never initialized at all (the common real-world case: no Arize
    # credentials configured) — must behave as a pure no-op.
    obs._enabled = False
    obs._tracer = None
    assert _do_real_work(21) == 42
    print("  PASS  tracing never initialized: wrapped function's real return value is unaffected")

    # 2. Tracing WAS initialized, but the tracer's start_as_current_span itself raises
    # on every call (simulating a fully broken Arize connection/auth) — the real
    # scenario the user asked to prove.
    class _BrokenTracer:
        def start_as_current_span(self, name):
            raise ConnectionError("simulated: Arize export connection broken")

    obs._enabled = True
    obs._tracer = _BrokenTracer()
    try:
        assert _do_real_work(21) == 42
        print("  PASS  span creation raising (simulated broken Arize connection): "
              "wrapped function's real return value is STILL unaffected")
    finally:
        obs._enabled = False
        obs._tracer = None

    # 3. Tracing initializes and span creation succeeds, but set_attribute on the REAL
    # span raises (simulating a malformed/oversized attribute value rejected by the
    # exporter) — must not propagate either.
    class _BrokenAttributeSpan:
        def set_attribute(self, key, value):
            raise ValueError("simulated: attribute value rejected")

    class _WorkingTracerBrokenAttrs:
        def start_as_current_span(self, name):
            return _FakeSpanCM(_BrokenAttributeSpan())

    obs._enabled = True
    obs._tracer = _WorkingTracerBrokenAttrs()
    try:
        assert _do_real_work(21) == 42
        print("  PASS  set_attribute raising on a real span: wrapped function's real "
              "return value is STILL unaffected")
    finally:
        obs._enabled = False
        obs._tracer = None


class _FakeSpanCM:
    """Minimal context-manager stand-in for what tracer.start_as_current_span(name)
    returns in the real OTel API — __enter__ returns the span object."""

    def __init__(self, span):
        self._span = span

    def __enter__(self):
        return self._span

    def __exit__(self, *exc):
        return False


def run_traced_span_never_swallows_real_errors_tests():
    print("\ntraced_span — the OTHER half of the promise: a genuine business exception "
          "still propagates normally, even with tracing completely broken:")

    class _BrokenTracer:
        def start_as_current_span(self, name):
            raise ConnectionError("simulated: Arize connection broken")

    obs._enabled = True
    obs._tracer = _BrokenTracer()
    try:
        try:
            with obs.traced_span("will_fail", "LLM") as span:
                span.set_attribute("x", "y")
                raise RuntimeError("a genuine business-logic failure, e.g. Feature Agent's own error")
            print("  FAIL  expected the genuine RuntimeError to propagate, it was swallowed")
            sys.exit(1)
        except RuntimeError as err:
            assert "genuine business-logic failure" in str(err)
            print(f"  PASS  a real exception from the wrapped code propagates normally, "
                  f"even with a fully broken tracer underneath: {err}")
    finally:
        obs._enabled = False
        obs._tracer = None


async def run_safe_eval_call_tests():
    print("\nsafe_eval_call — quality-judge calls fail without touching the real pipeline:")

    async def _working_judge():
        return {"score": 0.9, "reasons": "well grounded"}

    result = await obs.safe_eval_call(_working_judge, judge_name="test_judge")
    assert result == {"score": 0.9, "reasons": "well grounded"}
    print("  PASS  a successful judge call returns its real result")

    async def _broken_judge():
        raise TimeoutError("simulated: Anthropic API timeout")

    result2 = await obs.safe_eval_call(_broken_judge, judge_name="test_judge")
    assert result2 is None, "a failed judge call must return None, never raise, never fabricate a fake score"
    print("  PASS  a failing judge call (simulated API timeout) returns None, doesn't raise")


def run_attribute_builder_tests():
    print("\nAttribute builders — pure unit tests:")
    from openinference.semconv.trace import SpanAttributes

    attrs = obs.llm_span_attributes(
        model_name="claude-sonnet-5",
        usage={"input_tokens": 1000, "output_tokens": 200},
        invocation_parameters={"max_turns": 5, "permission_mode": "dontAsk"},
        input_value="the prompt", output_value="the response",
        total_cost_usd=0.012,
    )
    assert attrs[SpanAttributes.LLM_MODEL_NAME] == "claude-sonnet-5"
    assert attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] == 1000
    assert attrs[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] == 200
    assert attrs[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] == 1200
    assert attrs[SpanAttributes.LLM_COST_TOTAL] == 0.012
    assert SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ not in attrs, \
        "cache token keys must be ABSENT (not fabricated as 0) when the usage dict doesn't have them"
    print("  PASS  llm_span_attributes builds real token/cost fields, omits cache tokens "
          "entirely when not present in usage (never fabricates 0)")

    attrs_cached = obs.llm_span_attributes(
        model_name="claude-sonnet-5",
        usage={"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 800, "cache_creation_input_tokens": 50},
        invocation_parameters={}, input_value="x", output_value="y",
    )
    assert attrs_cached[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] == 800
    assert attrs_cached[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_WRITE] == 50
    print("  PASS  llm_span_attributes includes real cache-read/cache-write token counts when present in usage")

    tool_attrs = obs.tool_span_attributes("wit_query", "Query ADO work items", {"action": "wiql"})
    assert tool_attrs[SpanAttributes.TOOL_NAME] == "wit_query"
    print("  PASS  tool_span_attributes builds the expected tool.* fields")

    in_attrs = obs.input_value_attribute("the prompt")
    assert in_attrs[SpanAttributes.INPUT_VALUE] == "the prompt"
    out_attrs = obs.output_value_attribute({"k": "v"})
    assert out_attrs[SpanAttributes.OUTPUT_VALUE] == "{'k': 'v'}"
    print("  PASS  input_value_attribute/output_value_attribute build single-key dicts "
          "keyed by the real verified constants")

    eval_attrs = obs.evaluation_attributes([{"name": "groundedness", "score": 0.85, "explanation": "cites real evidence"}])
    assert eval_attrs["evaluations.0.evaluation.name"] == "groundedness"
    assert eval_attrs["evaluations.0.evaluation.score"] == 0.85
    assert eval_attrs["evaluations.0.evaluation.explanation"] == "cites real evidence"
    assert eval_attrs["evaluations.0.evaluation.annotator_kind"] == "LLM"
    print("  PASS  evaluation_attributes uses the REAL verified openinference.instrumentation."
          "get_evaluation_attributes mechanism, producing the real evaluations.0.evaluation.* keys")

    dual_attrs = obs.evaluation_attributes([
        {"name": "groundedness", "score": 0.9},
        {"name": "coherence", "score": 0.7},
    ])
    assert dual_attrs["evaluations.0.evaluation.name"] == "groundedness"
    assert dual_attrs["evaluations.0.evaluation.score"] == 0.9
    assert dual_attrs["evaluations.1.evaluation.name"] == "coherence"
    assert dual_attrs["evaluations.1.evaluation.score"] == 0.7
    print("  PASS  evaluation_attributes with TWO entries produces distinct evaluations.0.*/"
          "evaluations.1.* keys, not a collision — the real reason its signature takes a list")


def run_attribute_builders_never_raise_tests():
    print("\nAttribute builders — the OTHER real gap: every one of these is called "
          "UNCONDITIONALLY at every call site, often as an argument evaluated BEFORE "
          "traced_span() is even entered (e.g. traced_span(name, kind, "
          "obs.input_value_attribute(prompt))) — so they can't rely on traced_span's own "
          "try/except for protection. Forces the realistic failure mode (openinference not "
          "importable) and confirms each builder returns {} rather than raising:")

    import sys as _sys

    blocked = {
        "openinference.semconv.trace": _sys.modules.get("openinference.semconv.trace"),
        "openinference.instrumentation": _sys.modules.get("openinference.instrumentation"),
    }
    _sys.modules["openinference.semconv.trace"] = None
    _sys.modules["openinference.instrumentation"] = None
    try:
        assert obs.input_value_attribute("x") == {}
        assert obs.output_value_attribute("x") == {}
        assert obs.tool_span_attributes("t", "d", {}) == {}
        assert obs.llm_span_attributes("m", {}, {}, "in", "out") == {}
        assert obs.evaluation_attributes([{"name": "x", "score": 1.0}]) == {}
        print("  PASS  every attribute-builder returns {} (not a raise) when openinference "
              "is not importable — the realistic version of a missing/broken install, not "
              "just missing credentials")
    finally:
        for name, module in blocked.items():
            if module is None:
                _sys.modules.pop(name, None)
            else:
                _sys.modules[name] = module


async def main():
    print("common/observability.py — test suite\n")
    run_init_tracing_tests()
    run_traced_span_never_breaks_wrapped_code_tests()
    run_traced_span_never_swallows_real_errors_tests()
    await run_safe_eval_call_tests()
    run_attribute_builder_tests()
    run_attribute_builders_never_raise_tests()
    print("\nAll fail-safe and attribute-builder tests passed — observability is "
          "structurally incapable of breaking wrapped pipeline code, and does not "
          "swallow genuine business exceptions either.")


if __name__ == "__main__":
    asyncio.run(main())
