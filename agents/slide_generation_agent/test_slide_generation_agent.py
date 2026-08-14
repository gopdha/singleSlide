#!/usr/bin/env python3
"""
Mode 2 (render_report) is fully deterministic, zero LLM, zero MCP — its whole auto-fit
ladder (including the raise-at-cap SlideFitError case) gets genuine unit tests here, no
credentials needed, same testability tier as core/rag_rollup.py's test suite.

Mode 1 (run_slide_generation_discovery) gets the same 3-tier split as discovery_agent:
pure unit tests + a scripted-conversation integration tier here (the one agentic call,
_generate_candidates, mocked; write_skill/load_skill left real against a temp
skills_root). Genuine tier 3 — actually opening the 3 rendered .pptx candidates and
judging them as a PM would — is NOT automated; run slide_generation_agent.py's
`discover` subcommand yourself, see README.md.

Run with:
    python3 test_slide_generation_agent.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import slide_generation_agent as sga  # noqa: E402
from slide_generation_agent import (  # noqa: E402
    DEFAULT_ROW_PADDING_IN,
    LAYOUT_ARCHETYPES,
    SlideFitError,
    _estimate_block_height_in,
    _feature_rows,
    _fit_rows,
    _initiative_rows,
    _rag_hex,
    _status_counts,
    _status_hex,
    _truncate,
    _validate_flex_bounds,
    default_ask_human,
    render_report,
    run_slide_generation_discovery,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from skill_loader import load_skill, write_skill  # noqa: E402

TEST_PROJECT_ID = "slide-gen-test-project"

FIXTURE_DESIGN = {
    "palette": {"background": "#FFFFFF", "text_primary": "#1A1A1A", "text_secondary": "#5A5A5A",
                "brand_primary": "#0B3D91", "green": "#2E7D32", "amber": "#F9A825", "red": "#C62828", "needs_review": "#757575"},
    "fonts": {"heading_font": "Calibri", "body_font": "Calibri", "heading_size_pt": 28, "body_size_pt": 14},
    "flex_bounds": {"font_size_pt_min": 10, "row_height_in_min": 0.06, "display_text_max_chars_default": 220, "display_text_max_chars_min": 90},
}


def _design_for(archetype: str) -> dict:
    return {"layout_archetype": archetype, **FIXTURE_DESIGN}


def run_fit_heuristic_tests():
    print("Fit heuristic — pure unit tests (no credentials, no rendering):")

    h_short = _estimate_block_height_in("short text", 14, 10.0)
    h_long = _estimate_block_height_in("a" * 1000, 14, 10.0)
    assert h_long > h_short
    print("  PASS  _estimate_block_height_in grows with text length")

    h_small_font = _estimate_block_height_in("some text of a certain length here", 10, 5.0)
    h_big_font = _estimate_block_height_in("some text of a certain length here", 24, 5.0)
    assert h_big_font > h_small_font
    print("  PASS  _estimate_block_height_in grows with font size")

    assert _truncate("short", 100) == "short"
    assert _truncate("a" * 50, 10) == "a" * 9 + "…"
    assert len(_truncate("a" * 50, 10)) == 10
    print("  PASS  _truncate leaves short text alone, truncates long text to exactly max_chars with an ellipsis")

    fit = _fit_rows(
        ["a short row"], box_width_in=10.0, available_height_in=5.0,
        font_size_default=14, font_size_min=10, row_padding_default_in=0.14, row_padding_min_in=0.06,
        chars_default=220, chars_min=90, context="test",
    )
    assert fit.font_size_pt == 14 and fit.row_padding_in == 0.14 and fit.texts == ["a short row"]
    print("  PASS  _fit_rows returns defaults unchanged when content already fits")

    long_text = "word " * 80
    fit2 = _fit_rows(
        [long_text], box_width_in=10.0, available_height_in=0.5,
        font_size_default=14, font_size_min=8, row_padding_default_in=0.14, row_padding_min_in=0.06,
        chars_default=400, chars_min=400, context="test",
    )
    assert fit2.font_size_pt < 14
    print(f"  PASS  _fit_rows shrinks font size ({fit2.font_size_pt}pt) when content doesn't fit at the default")

    huge_text = "word " * 500
    fit3 = _fit_rows(
        [huge_text], box_width_in=10.0, available_height_in=0.4,
        font_size_default=14, font_size_min=13, row_padding_default_in=0.14, row_padding_min_in=0.14,
        chars_default=2500, chars_min=50, context="test",
    )
    assert len(fit3.texts[0]) <= 50
    print("  PASS  _fit_rows truncates text toward the character floor when font/padding shrinking alone isn't enough")

    try:
        _fit_rows(
            ["word " * 500], box_width_in=10.0, available_height_in=0.001,
            font_size_default=14, font_size_min=13, row_padding_default_in=0.14, row_padding_min_in=0.14,
            chars_default=2500, chars_min=2500, context="unfittable test",
        )
        print("  FAIL  expected SlideFitError, got none")
        sys.exit(1)
    except SlideFitError as err:
        assert "unfittable test" in str(err)
        print(f"  PASS  _fit_rows raises SlideFitError (never silently degrades further) when nothing in the bounded search fits: {err}")

    base_kwargs = dict(
        texts=["x"], box_width_in=10.0, available_height_in=5.0,
        font_size_default=14, font_size_min=10, row_padding_default_in=0.14, row_padding_min_in=0.06,
        chars_default=220, chars_min=90, context="invalid bounds test",
    )
    for override in (
        dict(font_size_default=8, font_size_min=10),
        dict(row_padding_default_in=0.05, row_padding_min_in=0.1),
        dict(chars_default=50, chars_min=100),
    ):
        kwargs = {**base_kwargs, **override}
        try:
            _fit_rows(**kwargs)
            print(f"  FAIL  expected ValueError for invalid bounds {override}, got none")
            sys.exit(1)
        except ValueError:
            pass
    print("  PASS  _fit_rows rejects invalid flex_bounds (a floor at/above its own default) for all 3 levers, loudly")


def run_validate_flex_bounds_tests():
    print("\n_validate_flex_bounds — pure unit tests (no credentials, no rendering):")

    def _candidate(font_size_pt_min=10, row_height_in_min=0.06, chars_default=220, chars_min=90):
        return {
            "name": "Test Candidate", "fonts": {"body_size_pt": 14, "heading_size_pt": 28},
            "flex_bounds": {"font_size_pt_min": font_size_pt_min, "row_height_in_min": row_height_in_min,
                             "display_text_max_chars_default": chars_default, "display_text_max_chars_min": chars_min},
        }

    _validate_flex_bounds(_candidate(), context="valid")  # must not raise
    print("  PASS  a well-formed candidate passes without raising")

    try:
        _validate_flex_bounds(_candidate(font_size_pt_min=20), context="bad font")
        print("  FAIL  expected ValueError for font_size_pt_min above body_size_pt, got none")
        sys.exit(1)
    except ValueError as err:
        assert "font_size_pt_min" in str(err)
        print(f"  PASS  rejects font_size_pt_min above body_size_pt: {err}")

    # Regression: the real live bug — a candidate proposed row_height_in_min (0.28) above
    # the code's own default row padding, self-contradictory regardless of content, caught
    # only mid-render deep inside _fit_rows before this check existed.
    try:
        _validate_flex_bounds(_candidate(row_height_in_min=0.28), context="bad row height")
        print("  FAIL  expected ValueError for row_height_in_min above the render default, got none")
        sys.exit(1)
    except ValueError as err:
        assert "row_height_in_min" in str(err)
        print(f"  PASS  regression: rejects row_height_in_min ({0.28}) above DEFAULT_ROW_PADDING_IN ({DEFAULT_ROW_PADDING_IN}): {err}")

    try:
        _validate_flex_bounds(_candidate(chars_default=50, chars_min=100), context="bad chars")
        print("  FAIL  expected ValueError for display_text_max_chars_min above its default, got none")
        sys.exit(1)
    except ValueError as err:
        assert "display_text_max_chars_min" in str(err)
        print(f"  PASS  rejects display_text_max_chars_min above display_text_max_chars_default: {err}")

    try:
        _validate_flex_bounds(_candidate(font_size_pt_min=20, row_height_in_min=0.28), context="multi-bad")
        print("  FAIL  expected ValueError for multiple simultaneous violations, got none")
        sys.exit(1)
    except ValueError as err:
        assert "font_size_pt_min" in str(err) and "row_height_in_min" in str(err)
        print(f"  PASS  reports every violated lever at once, not just the first: {err}")


async def run_generate_candidates_validation_regression_test():
    print("\n_generate_candidates — forced-violation regression test (same pattern as "
          "critique_agent's risk-floor test):")

    # Candidate 2 carries the exact real-bug shape: row_height_in_min above the render
    # default. Candidates 1 and 3 are well-formed — proves the check inspects EVERY
    # candidate, not just the first, and that one bad candidate fails the whole batch.
    bad_result = {"candidates": [
        {"name": "Candidate 1", "rationale": "x", "palette": FIXTURE_DESIGN["palette"], "fonts": FIXTURE_DESIGN["fonts"],
         "flex_bounds": {"font_size_pt_min": 10, "row_height_in_min": 0.06, "display_text_max_chars_default": 220, "display_text_max_chars_min": 90}},
        {"name": "Candidate 2", "rationale": "x", "palette": FIXTURE_DESIGN["palette"], "fonts": FIXTURE_DESIGN["fonts"],
         "flex_bounds": {"font_size_pt_min": 10, "row_height_in_min": 0.28, "display_text_max_chars_default": 220, "display_text_max_chars_min": 90}},
        {"name": "Candidate 3", "rationale": "x", "palette": FIXTURE_DESIGN["palette"], "fonts": FIXTURE_DESIGN["fonts"],
         "flex_bounds": {"font_size_pt_min": 10, "row_height_in_min": 0.06, "display_text_max_chars_default": 220, "display_text_max_chars_min": 90}},
    ]}

    build_calls = []
    real_build_and_save = sga._build_and_save

    def _tracking_build_and_save(*args, **kwargs):
        build_calls.append(1)
        return real_build_and_save(*args, **kwargs)

    async def _fake_run_agentic_call(*args, **kwargs):
        return bad_result

    real_run_agentic_call = sga._run_agentic_call
    sga._run_agentic_call = _fake_run_agentic_call
    sga._build_and_save = _tracking_build_and_save
    try:
        try:
            await sga._generate_candidates("regression-project", "claude-sonnet-5")
            print("  FAIL  expected ValueError for candidate 2's self-contradictory row_height_in_min, got none")
            sys.exit(1)
        except ValueError as err:
            assert "Candidate 2" in str(err) and "row_height_in_min" in str(err)
            assert len(build_calls) == 0, "validation must reject the batch BEFORE any render is attempted"
            print(f"  PASS  _generate_candidates rejects a self-contradictory candidate immediately after "
                  f"the agentic call returns, deterministically, before any render is attempted "
                  f"(build_calls={len(build_calls)}): {err}")
    finally:
        sga._run_agentic_call = real_run_agentic_call
        sga._build_and_save = real_build_and_save


def run_design_prompt_tests():
    print("\nDESIGN_SYSTEM_PROMPT — structural check (no credentials, no API call):")

    # Regression: two consecutive live runs had the model guess a plausible-sounding
    # row_height_in_min (0.28, then 0.24) with no real anchor — the prompt described the
    # constraint in prose ("a comfortable default") but never stated the actual
    # DEFAULT_ROW_PADDING_IN value being compared against, unlike font_size_pt_min and
    # display_text_max_chars_min, which compare against values the model proposes itself
    # in the same response. _validate_flex_bounds catching the violation is necessary but
    # not sufficient — the model needs the real number to satisfy, not a guess. This check
    # guards against the prompt regressing back to vague prose with no anchor.
    assert str(DEFAULT_ROW_PADDING_IN) in sga.DESIGN_SYSTEM_PROMPT, \
        "DESIGN_SYSTEM_PROMPT must state the real DEFAULT_ROW_PADDING_IN value the model " \
        "needs to stay under, not just describe the constraint in vague prose"
    print(f"  PASS  DESIGN_SYSTEM_PROMPT states the real DEFAULT_ROW_PADDING_IN value ({DEFAULT_ROW_PADDING_IN}) "
          f"the model must stay under, not just a vague description of the constraint")


def run_design_helper_tests():
    print("\nDesign-derived helpers — pure unit tests:")
    design = _design_for("single_column_narrative")

    assert _status_hex(design, "On Track") == design["palette"]["green"]
    assert _status_hex(design, "At Risk") == design["palette"]["amber"]
    assert _status_hex(design, "Blocked") == design["palette"]["red"]
    assert _status_hex(design, "Needs Human Review") == design["palette"]["needs_review"]
    print("  PASS  _status_hex maps all 4 taxonomy labels to distinct palette colors")

    assert _rag_hex(design, "Green") == design["palette"]["green"]
    assert _rag_hex(design, "Unknown") == design["palette"]["needs_review"]
    print("  PASS  _rag_hex maps all 4 rag_rollup outcomes (including Unknown) to distinct palette colors")

    features = [
        {"feature_id": 1, "title": "A", "status_label": "On Track", "display_text": "x"},
        {"feature_id": 2, "title": "B", "status_label": "At Risk", "display_text": "y"},
        {"feature_id": 3, "title": "C", "status_label": "At Risk", "display_text": "z"},
    ]
    counts = _status_counts(features)
    assert counts == {"On Track": 1, "At Risk": 2, "Blocked": 0, "Needs Human Review": 0}
    print("  PASS  _status_counts tallies every taxonomy label, including zero-count ones")

    rows = _feature_rows(features, design)
    assert len(rows) == 3 and rows[0]["color_hex"] == design["palette"]["green"]
    assert "On Track" in rows[0]["title"]
    print("  PASS  _feature_rows attaches the correct status color and label to each row")

    initiatives = [{"title": "Init A", "display_text": "details"}]
    irows = _initiative_rows(initiatives, design)
    assert irows[0]["color_hex"] == design["palette"]["brand_primary"]
    print("  PASS  _initiative_rows uses brand_primary (Initiatives carry no status label)")


def run_default_ask_human_tests():
    print("\ndefault_ask_human — input-validation logic (monkeypatched stdin):")
    import builtins

    original_input = builtins.input
    try:
        answers = iter(["2"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Alpha", "Beta", "Gamma"]) == "Beta"
        print("  PASS  numeric selection returns the corresponding option")

        answers = iter(["nonsense", "Alpha"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Alpha", "Beta"]) == "Alpha"
        print("  PASS  invalid input is rejected and re-prompted, never silently accepted")
    finally:
        builtins.input = original_input


def run_render_report_tests(skills_root: str):
    print("\nrender_report (Mode 2) — fully deterministic, no credentials, no LLM:")

    sample = sga._sample_report_fixture(TEST_PROJECT_ID)

    for archetype in LAYOUT_ARCHETYPES:
        pid = f"{TEST_PROJECT_ID}-{archetype}"
        write_skill(pid, sga.SKILL_NAME, _design_for(archetype), "Design rationale.", skills_root=skills_root)
        with tempfile.TemporaryDirectory() as out_dir:
            path = render_report(sample, pid, skills_root=skills_root, output_path=Path(out_dir) / "out.pptx")
            assert path.exists() and path.stat().st_size > 0
        print(f"  PASS  {archetype}: render_report produces a real, non-empty .pptx for the sample fixture")

    try:
        with tempfile.TemporaryDirectory() as out_dir:
            render_report(sample, "no-such-project", skills_root=skills_root, output_path=Path(out_dir) / "out.pptx")
        print("  FAIL  expected FileNotFoundError for a project with no locked skill, got none")
        sys.exit(1)
    except FileNotFoundError:
        print("  PASS  render_report raises FileNotFoundError for a project with no locked slide-generation-agent skill")

    huge_pid = f"{TEST_PROJECT_ID}-overflow"
    write_skill(huge_pid, sga.SKILL_NAME, _design_for("single_column_narrative"), "x", skills_root=skills_root)
    overflow_report = dict(sample)
    overflow_report["curated_features"] = [
        {"feature_id": i, "title": f"Feature {i}", "status_label": "On Track", "display_text": "word " * 60}
        for i in range(100)
    ]
    try:
        with tempfile.TemporaryDirectory() as out_dir:
            render_report(overflow_report, huge_pid, skills_root=skills_root, output_path=Path(out_dir) / "out.pptx")
        print("  FAIL  expected SlideFitError for 100 features with long display_text, got none")
        sys.exit(1)
    except SlideFitError as err:
        print(f"  PASS  render_report raises SlideFitError (Requirement 16 escalation) when content genuinely can't fit: {err}")

    empty_pid = f"{TEST_PROJECT_ID}-empty"
    write_skill(empty_pid, sga.SKILL_NAME, _design_for("banner_header_grid"), "x", skills_root=skills_root)
    empty_report = dict(sample)
    empty_report["curated_features"] = []
    empty_report["curated_initiatives"] = []
    with tempfile.TemporaryDirectory() as out_dir:
        path = render_report(empty_report, empty_pid, skills_root=skills_root, output_path=Path(out_dir) / "out.pptx")
        assert path.exists()
    print("  PASS  empty curated_features/curated_initiatives renders an empty-state slide instead of crashing")


class _ScriptedAskHuman:
    """Same instinct as discovery_agent's own test helper — records every question asked
    (for order/content assertions) and pops canned answers in sequence."""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.questions_asked: list[tuple] = []

    def __call__(self, question, options=None):
        self.questions_asked.append((question, options))
        if not self.answers:
            raise AssertionError(f"Ran out of scripted answers at question: {question!r}")
        return self.answers.pop(0)


class _MockGenerateCandidates:
    """Monkeypatches the one agentic call Mode 1 makes (_generate_candidates) —
    write_skill/load_skill are left REAL against a temp skills_root, so persistence is
    genuinely exercised. Deterministic: same 3 candidates (one per archetype, in order)
    every call, unless overridden per index."""

    def __init__(self, candidate_overrides: dict | None = None):
        self.calls = 0
        self.candidate_overrides = candidate_overrides or {}

    async def __call__(self, project_id, model, debug=False):
        self.calls += 1
        candidates = []
        for i, archetype in enumerate(LAYOUT_ARCHETYPES):
            base = {"name": f"Candidate {i + 1}", "rationale": f"Rationale for candidate {i + 1}.",
                    "layout_archetype": archetype, **FIXTURE_DESIGN}
            base.update(self.candidate_overrides.get(i, {}))
            candidates.append(base)
        return candidates

    def __enter__(self):
        self._original = sga._generate_candidates
        sga._generate_candidates = self
        return self

    def __exit__(self, *exc):
        sga._generate_candidates = self._original


async def run_discovery_integration_tests(skills_root: str):
    print("\nrun_slide_generation_discovery (Mode 1) — scripted-conversation integration tests:")

    # 1. Happy path — pick candidate 2 (two_column_metrics_sidebar)
    scripted = _ScriptedAskHuman(["2", "Preferred the sidebar layout for at-a-glance status.", "Yes, persist"])
    with _MockGenerateCandidates():
        path = await run_slide_generation_discovery(
            TEST_PROJECT_ID + "-happy", ask_human=scripted, skills_root=skills_root, output_dir=Path(tempfile.mkdtemp()),
        )
    assert path.exists()
    skill = load_skill(TEST_PROJECT_ID + "-happy", sga.SKILL_NAME, skills_root=skills_root)
    assert skill.frontmatter["layout_archetype"] == "two_column_metrics_sidebar"
    assert "Preferred the sidebar layout" in skill.body
    print("  PASS  happy path: picking candidate 2 locks in two_column_metrics_sidebar, "
          "PM's stated reasoning survives into the persisted body")

    # 2. Regenerate loop — reject the first batch, pick from the second
    scripted2 = _ScriptedAskHuman(["Regenerate", "1", "", "Yes, persist"])
    with _MockGenerateCandidates() as mock2:
        await run_slide_generation_discovery(
            TEST_PROJECT_ID + "-regen", ask_human=scripted2, skills_root=skills_root, output_dir=Path(tempfile.mkdtemp()),
        )
    assert mock2.calls == 2
    skill2 = load_skill(TEST_PROJECT_ID + "-regen", sga.SKILL_NAME, skills_root=skills_root)
    assert skill2.frontmatter["layout_archetype"] == "single_column_narrative"
    print("  PASS  regenerate loop: rejecting the first batch produces a genuine second call, "
          "then picking from the new batch persists correctly")

    # 3. Cancel before persist — nothing written
    scripted3 = _ScriptedAskHuman(["1", "", "No, cancel"])
    with _MockGenerateCandidates():
        try:
            await run_slide_generation_discovery(
                TEST_PROJECT_ID + "-cancel", ask_human=scripted3, skills_root=skills_root, output_dir=Path(tempfile.mkdtemp()),
            )
            print("  FAIL  expected RuntimeError when the PM cancels before persisting, got none")
            sys.exit(1)
        except RuntimeError as err:
            assert "cancelled" in str(err).lower()
            cancelled_path = Path(skills_root) / (TEST_PROJECT_ID + "-cancel") / sga.SKILL_NAME / "SKILL.md"
            assert not cancelled_path.exists(), "cancelling must not leave a persisted skill file behind"
            print(f"  PASS  cancelling before the final persist confirmation raises and writes nothing: {err}")

    # 4. One candidate fails to render — the PM must still be able to pick among the
    # surviving 2, not have the whole flow crash. Forced directly at _build_and_save
    # (rather than via flex_bounds tuning against the fixture content, which would be
    # fragile and content-dependent) to test run_slide_generation_discovery's own
    # per-candidate try/except in isolation from the fit heuristic's specifics.
    real_build_and_save = sga._build_and_save

    def _flaky_build_and_save(report, design, output_path, debug=False):
        if design["layout_archetype"] == "two_column_metrics_sidebar":
            raise SlideFitError("forced failure for test coverage")
        return real_build_and_save(report, design, output_path, debug=debug)

    scripted4 = _ScriptedAskHuman(["1", "", "Yes, persist"])
    sga._build_and_save = _flaky_build_and_save
    try:
        with _MockGenerateCandidates():
            await run_slide_generation_discovery(
                TEST_PROJECT_ID + "-partial-fail", ask_human=scripted4, skills_root=skills_root, output_dir=Path(tempfile.mkdtemp()),
            )
    finally:
        sga._build_and_save = real_build_and_save

    questions = [q for q, _ in scripted4.questions_asked]
    assert any("2 template candidate(s) rendered" in q for q in questions), \
        "only 2 of 3 candidates should have survived rendering, and the PM must be told exactly that"
    print("  PASS  a candidate that fails to render (SlideFitError) is dropped, not fatal — "
          "the PM picks among the ones that actually rendered")

    # 5. ALL candidates fail to render — must offer regenerate-or-cancel, never crash
    def _always_fail_build_and_save(report, design, output_path, debug=False):
        raise SlideFitError("forced failure for test coverage")

    scripted5 = _ScriptedAskHuman(["No, cancel"])
    sga._build_and_save = _always_fail_build_and_save
    try:
        with _MockGenerateCandidates():
            try:
                await run_slide_generation_discovery(
                    TEST_PROJECT_ID + "-all-fail", ask_human=scripted5, skills_root=skills_root, output_dir=Path(tempfile.mkdtemp()),
                )
                print("  FAIL  expected RuntimeError when every candidate fails to render, got none")
                sys.exit(1)
            except RuntimeError as err:
                assert "no candidate could be rendered" in str(err).lower()
                print(f"  PASS  every candidate failing to render offers regenerate-or-cancel, never crashes: {err}")
    finally:
        sga._build_and_save = real_build_and_save


async def run_isolation_mode_test():
    """Mechanically proves the SDK-isolation fix (CLAUDE.md 'Known gotchas' CRITICAL entry)
    is wired on Mode 1's one real query() call site (_run_agentic_call, shared by
    _generate_candidates) — no credentials needed, query() is mocked so nothing hits the
    network."""
    print("\nSDK isolation mode — mechanical proof (no credentials, query() is mocked):")

    from claude_agent_sdk.types import ResultMessage

    captured_options = []

    async def _fake_query(*, prompt, options):
        captured_options.append(options)
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="fake", structured_output={"ok": True},
        )

    original_query = sga.query
    sga.query = _fake_query
    try:
        await sga._run_agentic_call(
            prompt="test", system_prompt="test", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
            model="claude-sonnet-5", max_turns=3, caller_name="test",
        )
        assert len(captured_options) == 1, f"expected exactly 1 real query() call, got {len(captured_options)}"
        opts = captured_options[0]
        assert opts.setting_sources == [], f"expected setting_sources=[], got {opts.setting_sources}"
        assert opts.skills == [], f"expected skills=[], got {opts.skills}"
        assert opts.strict_mcp_config is True, f"expected strict_mcp_config=True, got {opts.strict_mcp_config}"
        print("  PASS  _run_agentic_call's real query() call carries setting_sources=[], skills=[], "
              "strict_mcp_config=True (SDK isolation mode)")
    finally:
        sga.query = original_query


async def main():
    print("Slide Generation Agent — test suite\n")
    run_fit_heuristic_tests()
    run_validate_flex_bounds_tests()
    run_design_prompt_tests()
    run_design_helper_tests()
    run_default_ask_human_tests()
    await run_isolation_mode_test()
    await run_generate_candidates_validation_regression_test()

    with tempfile.TemporaryDirectory() as skills_root:
        run_render_report_tests(skills_root)
        await run_discovery_integration_tests(skills_root)

    print("\nAll pure unit, render_report, and scripted-conversation integration tests passed.")
    print("\nGenuine tier 3 (opening the 3 rendered .pptx candidates and judging them as a PM "
          "would) is NOT automated — run: python3 slide_generation_agent.py discover <project_id>")


if __name__ == "__main__":
    asyncio.run(main())
