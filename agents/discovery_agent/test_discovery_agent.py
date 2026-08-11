#!/usr/bin/env python3
"""
Pure unit tests (WIQL-sampling helpers, value-frequency counting, operator derivation,
default_ask_human's input-validation logic) always run — no credentials, no network.

The integration tier scripts a queue of canned ask_human answers and mocks every
external call (ADO sampling, list_committed_features, parse_slide, the body-drafting
Anthropic call) — proves the full conversation flow, the validate-reject-retry loop, and
write_skill/load_skill round-tripping actually work, with zero real credentials needed.

Genuine tier 3 is NOT automated here, deliberately: it needs a live human conversation,
not just credentials. Run agents/discovery_agent/discovery_agent.py directly yourself —
see README.md.

Run with:
    python3 test_discovery_agent.py
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import discovery_agent as da  # noqa: E402
from discovery_agent import (  # noqa: E402
    _append_caveats,
    _derive_filter_operator,
    _extract_items,
    _get,
    _normalize_field_name,
    _resolve_field,
    _value_frequency,
    default_ask_human,
    run_feature_agent_discovery,
    run_status_report_agent_discovery,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from skill_loader import load_skill  # noqa: E402

TEST_PROJECT_ID = "discovery-test-project"

FAKE_ADO_SAMPLE = [
    {"fields": {"System.Id": 101, "System.Title": "Build Agentic Dashboard", "System.Tags": "Committed",
                "System.State": "Active", "Microsoft.VSTS.Scheduling.StoryPoints": 5}},
    {"fields": {"System.Id": 205, "System.Title": "Vendor Integration Overhaul", "System.Tags": "Committed; Stretch",
                "System.State": "New", "Microsoft.VSTS.Scheduling.StoryPoints": 3}},
    {"fields": {"System.Id": 310, "System.Title": "Internal Tooling Cleanup", "System.Tags": "Backlog",
                "System.State": "New", "Microsoft.VSTS.Scheduling.StoryPoints": 2}},
]

# Same Tags shape as FAKE_ADO_SAMPLE (so the entry-criteria portion of the flow behaves
# identically), but Story Points empty on every item — triggers the sanity-check branch.
FAKE_ADO_SAMPLE_NO_STORY_POINTS = [
    {"fields": {"System.Id": 101, "System.Title": "Build Agentic Dashboard", "System.Tags": "Committed",
                "System.State": "Active", "Microsoft.VSTS.Scheduling.StoryPoints": None}},
    {"fields": {"System.Id": 205, "System.Title": "Vendor Integration Overhaul", "System.Tags": "Committed",
                "System.State": "New", "Microsoft.VSTS.Scheduling.StoryPoints": None}},
]

FAKE_PARSE_RESULT = {
    "team_lead_id": "Test Lead",
    "sections": {"accomplishments": ["Did a thing"], "planned_next": [], "risks": [], "help_needed": []},
    "tables": [], "color_cues": [], "parse_confidence": 0.25,
    "missing_sections": ["planned_next", "risks", "help_needed"], "slide_count_in_deck": 1,
}


def run_pure_unit_tests():
    print("Pure unit tests (WIQL sampling helpers, no credentials):")

    assert _derive_filter_operator("Tags") == "CONTAINS"
    assert _derive_filter_operator("tags") == "CONTAINS"
    assert _derive_filter_operator("State") == "="
    assert _derive_filter_operator("Priority") == "="
    print("  PASS  _derive_filter_operator: CONTAINS for Tags (case-insensitive), '=' otherwise")

    freq = _value_frequency(FAKE_ADO_SAMPLE, "Tags", split_multi=True)
    assert freq == {"Committed": 2, "Stretch": 1, "Backlog": 1}, freq
    print("  PASS  _value_frequency splits multi-value Tags on ';' (real ADO convention) and counts correctly")

    freq_state = _value_frequency(FAKE_ADO_SAMPLE, "State", split_multi=False)
    assert freq_state == {"Active": 1, "New": 2}, freq_state
    print("  PASS  _value_frequency treats single-value fields (State) as one value each, no splitting")

    assert _value_frequency([], "Tags", split_multi=True) == {}
    assert _value_frequency([{"fields": {}}], "Tags", split_multi=True) == {}
    print("  PASS  _value_frequency handles empty input and missing/empty field values without error")

    assert _extract_items([1, 2]) == [1, 2]
    assert _extract_items({"workItems": [1, 2]}) == [1, 2]
    assert _extract_items({"value": [3]}) == [3]
    assert _extract_items({"nothing_useful": True}) == []
    print("  PASS  _extract_items unwraps list/workItems/value/results shapes, empty on unrecognized dicts")

    assert _get({"fields": {"System.Title": "X"}}, "System.Title", "title") == "X"
    assert _get({"title": "Y"}, "System.Title", "title") == "Y"
    assert _get({"fields": {}}, "System.Title", "title") is None
    print("  PASS  _get resolves dotted-field-in-fields-dict, then flat-key fallback")

    # Regression: a real live run crashed on the PM answering "Tag" (singular) — see
    # docs/DECISION_LOG.md for the full writeup.
    assert _normalize_field_name("Tag") == "Tags"
    assert _normalize_field_name("tag") == "Tags"
    assert _normalize_field_name("TAGS") == "Tags"
    assert _normalize_field_name("  Tags  ") == "Tags"
    assert _normalize_field_name("State") == "State"
    assert _normalize_field_name("status") == "State"
    assert _normalize_field_name("Custom.PI.Field") == "Custom.PI.Field", \
        "an unrecognized (e.g. custom/PI) field name must pass through as typed, not be forced into a wrong bucket"
    print("  PASS  _normalize_field_name handles case/plural variants of Tag(s)/State, "
          "and passes unrecognized (custom) field names through unchanged")

    assert _resolve_field("Tag") == "System.Tag", \
        "_resolve_field itself is intentionally NOT synonym-aware (only case-insensitive) — " \
        "normalization is _normalize_field_name's job, applied once upstream, not duplicated here"
    assert _resolve_field("TAGS") == "System.Tags"
    assert _resolve_field("tags") == "System.Tags"
    print("  PASS  _resolve_field is case-insensitive (defense in depth) but not plural-aware — "
          "that's _normalize_field_name's job, applied once, not re-solved at every layer")

    assert _append_caveats("Body text.", []) == "Body text.", "no caveats must leave the body untouched"
    result = _append_caveats("Body text.", ["Caveat one.", "Caveat two."])
    assert "Body text." in result and "Caveat one." in result and "Caveat two." in result
    assert "Discovery caveats" in result
    print("  PASS  _append_caveats guarantees every caveat is present in the body — deterministic, "
          "not reliant on the (mocked-in-tests, real-elsewhere) drafting call having included it")


def run_default_ask_human_tests():
    print("\ndefault_ask_human — input-validation logic (monkeypatched stdin):")
    import builtins

    original_input = builtins.input
    try:
        answers = iter(["2"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Alpha", "Beta", "Gamma"]) == "Beta"
        print("  PASS  numeric selection returns the corresponding option")

        answers = iter(["Gamma"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Alpha", "Beta", "Gamma"]) == "Gamma"
        print("  PASS  exact option text is accepted directly")

        answers = iter(["nonsense", "99", "Alpha"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Alpha", "Beta"]) == "Alpha"
        print("  PASS  invalid input (garbage, out-of-range number) is rejected and re-prompted, never silently accepted")

        answers = iter(["  some free text  "])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Describe:") == "some free text"
        print("  PASS  free-text question (no options) returns stripped raw input")
    finally:
        builtins.input = original_input


class _ScriptedAskHuman:
    """Records every question asked (for order/content assertions) and pops canned
    answers in sequence — the same instinct as this project's other mocked-call tests
    (asserting the code took the path it should, not just that it produced some output)."""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.questions_asked: list[tuple] = []

    def __call__(self, question, options=None):
        self.questions_asked.append((question, options))
        if not self.answers:
            raise AssertionError(f"Ran out of scripted answers at question: {question!r}")
        return self.answers.pop(0)


class _MockExternalCalls:
    """Monkeypatches every real external call discovery_agent.py makes (ADO, ppt_mcp,
    Anthropic) — write_skill/load_skill are left REAL, against a real temp skills_root,
    so the actual persistence/round-trip mechanics are genuinely exercised."""

    def __init__(self, ado_sample=None, parse_result=None, found_features=None, draft_body="Generated body text."):
        self.ado_sample = ado_sample if ado_sample is not None else FAKE_ADO_SAMPLE
        self.parse_result = parse_result if parse_result is not None else FAKE_PARSE_RESULT
        self.found_features = found_features if found_features is not None else [
            {"id": 101, "title": "Build Agentic Dashboard"}, {"id": 205, "title": "Vendor Integration Overhaul"},
        ]
        self.draft_body = draft_body
        self.draft_body_calls: list[dict] = []

    async def _fake_sample(self, org, project, pat_base64, work_item_type, fields, debug=False):
        return self.ado_sample

    async def _fake_list_committed_features(self, org, project, pat_base64, project_id, skills_root=None, debug=False):
        return self.found_features

    async def _fake_parse_sample_report(self, sample_report_path, debug=False):
        return self.parse_result

    async def _fake_draft_skill_body(self, context, reference_example, skill_kind, model):
        self.draft_body_calls.append({"context": context, "skill_kind": skill_kind})
        return self.draft_body

    def __enter__(self):
        self._originals = {
            "_sample_work_items_by_type": da._sample_work_items_by_type,
            "list_committed_features": da.list_committed_features,
            "_parse_sample_report": da._parse_sample_report,
            "_draft_skill_body": da._draft_skill_body,
        }
        da._sample_work_items_by_type = self._fake_sample
        da.list_committed_features = self._fake_list_committed_features
        da._parse_sample_report = self._fake_parse_sample_report
        da._draft_skill_body = self._fake_draft_skill_body
        return self

    def __exit__(self, *exc):
        for name, fn in self._originals.items():
            setattr(da, name, fn)


async def run_feature_agent_discovery_integration_tests(skills_root: str):
    print("\nrun_feature_agent_discovery — scripted-conversation integration tests:")

    # 1. Happy path
    scripted = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child",
        "Microsoft.VSTS.Scheduling.StoryPoints", "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls() as mocks:
        path = await run_feature_agent_discovery(
            TEST_PROJECT_ID, "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted, skills_root=skills_root,
        )
    assert path.exists()
    skill = load_skill(TEST_PROJECT_ID, "feature-agent", skills_root=skills_root)
    assert skill.frontmatter["entry_criteria"] == {
        "work_item_type": "Feature", "filter_field": "Tags", "filter_operator": "CONTAINS", "filter_value": "Committed",
    }
    assert skill.frontmatter["hierarchy"]["child_types"] == ["Story", "Bug"]
    assert skill.body == "Generated body text."
    assert len(mocks.draft_body_calls) == 1 and mocks.draft_body_calls[0]["skill_kind"] == "Feature Agent"
    print("  PASS  happy path: real write_skill/load_skill round-trip produced the expected "
          "entry_criteria (CONTAINS operator correctly derived, not asked) and hierarchy")

    # 2. Validation reject-then-accept loop
    scripted2 = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child", "Microsoft.VSTS.Scheduling.StoryPoints",
        "No, let's adjust", "Stretch",  # reject the first proposal, pick a different real value
        "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls() as mocks2:
        await run_feature_agent_discovery(
            TEST_PROJECT_ID + "-reject", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted2, skills_root=skills_root,
        )
    skill2 = load_skill(TEST_PROJECT_ID + "-reject", "feature-agent", skills_root=skills_root)
    assert skill2.frontmatter["entry_criteria"]["filter_value"] == "Stretch"
    print("  PASS  validation reject-and-retry loop: rejecting the first proposal and picking a "
          "different real value correctly ends up in the persisted frontmatter")

    # 3. Cancel before persist — nothing gets written
    scripted3 = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child",
        "Microsoft.VSTS.Scheduling.StoryPoints", "Yes, this is correct", "No, cancel",
    ])
    with _MockExternalCalls() as mocks3:
        try:
            await run_feature_agent_discovery(
                TEST_PROJECT_ID + "-cancel", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
                ask_human=scripted3, skills_root=skills_root,
            )
            print("  FAIL  expected RuntimeError when the PM cancels before persisting, got none")
            sys.exit(1)
        except RuntimeError as err:
            assert "cancelled" in str(err).lower()
            cancelled_skill_path = Path(skills_root) / (TEST_PROJECT_ID + "-cancel") / "feature-agent" / "SKILL.md"
            assert not cancelled_skill_path.exists(), "cancelling must not leave a persisted skill file behind"
            print(f"  PASS  cancelling before the final persist confirmation raises and writes nothing: {err}")

    # 4. Regression: real live run crashed here — PM answered "Tag" (singular) and the
    # OLD code matched it against _FIELD_MAP exactly, found nothing, resolved to the
    # nonexistent "System.Tag", sampled zero real values, and raised. Two things must now
    # both hold: (a) "Tag" is a real option in the (now closed) choice list, not a free-text
    # guess, and (b) whatever text arrives is still normalized correctly regardless of path.
    scripted4 = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child",
        "Microsoft.VSTS.Scheduling.StoryPoints", "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls() as mocks4:
        await run_feature_agent_discovery(
            TEST_PROJECT_ID + "-tag-singular", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted4, skills_root=skills_root,
        )
    skill4 = load_skill(TEST_PROJECT_ID + "-tag-singular", "feature-agent", skills_root=skills_root)
    assert skill4.frontmatter["entry_criteria"]["filter_field"] == "Tags", \
        "the PM's 'Tag' (singular) answer must be normalized to the canonical 'Tags' in the PERSISTED " \
        "skill — otherwise every future weekly feature_agent run against this skill would silently " \
        "resolve to the nonexistent System.Tag field and find zero Features, forever"
    assert skill4.frontmatter["entry_criteria"]["filter_operator"] == "CONTAINS"
    print("  PASS  regression: 'Tag' (singular) no longer crashes, and — critically — the PERSISTED "
          "skill stores the canonical 'Tags', not the literal 'Tag' the PM typed (this matters beyond "
          "Discovery's own run: feature_agent.py's OWN _resolve_field is exact-match too, so an "
          "unnormalized 'Tag' would have silently broken every future weekly run against this skill)")

    # Same normalization must also hold when reached via the "Something else" free-text
    # escape hatch, not just the closed "Tag"/"State" options — a PM could type "tag",
    # "TAG", etc. there too.
    scripted5 = _ScriptedAskHuman([
        "Feature", "Something else", "tag", "Committed", "Story, Bug", "Child",
        "Microsoft.VSTS.Scheduling.StoryPoints", "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls() as mocks5:
        await run_feature_agent_discovery(
            TEST_PROJECT_ID + "-tag-freetext", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted5, skills_root=skills_root,
        )
    skill5 = load_skill(TEST_PROJECT_ID + "-tag-freetext", "feature-agent", skills_root=skills_root)
    assert skill5.frontmatter["entry_criteria"]["filter_field"] == "Tags"
    print("  PASS  normalization also holds via the 'Something else' free-text escape hatch "
          "(lowercase 'tag' -> canonical 'Tags'), not just the two closed-choice options")

    # 6. story_points_field sanity check fires (empty on every sample) and the PM keeps it
    # anyway — the resulting caveat must survive into the PERSISTED body. _draft_skill_body
    # is mocked to return a canned "Generated body text." string with NO mention of the
    # caveat at all — this test only passes if _append_caveats's deterministic guarantee is
    # what's doing the work, not the (real, unmockable-in-this-tier) LLM having listened.
    scripted6 = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child", "Microsoft.VSTS.Scheduling.StoryPoints",
        "Keep it anyway", "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls(ado_sample=FAKE_ADO_SAMPLE_NO_STORY_POINTS) as mocks6:
        await run_feature_agent_discovery(
            TEST_PROJECT_ID + "-sp-caveat", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted6, skills_root=skills_root,
        )
    assert len(mocks6.draft_body_calls) == 1
    passed_caveats = mocks6.draft_body_calls[0]["context"]["discovery_caveats"]
    assert len(passed_caveats) == 1 and "Microsoft.VSTS.Scheduling.StoryPoints" in passed_caveats[0]
    skill6 = load_skill(TEST_PROJECT_ID + "-sp-caveat", "feature-agent", skills_root=skills_root)
    assert "Discovery caveats" in skill6.body
    assert "Microsoft.VSTS.Scheduling.StoryPoints" in skill6.body and "empty" in skill6.body
    print("  PASS  story_points_field sanity-check-failed-but-kept-anyway: the caveat reaches "
          "the drafting context AND survives into the persisted body even though the mocked "
          "draft call's own canned output never mentioned it — the guarantee is deterministic")

    # 7. Providing a different field name instead is a DIFFERENT branch — no caveat should
    # be recorded, since the PM corrected the gap rather than overriding it.
    scripted7 = _ScriptedAskHuman([
        "Feature", "Tag", "Committed", "Story, Bug", "Child", "Microsoft.VSTS.Scheduling.StoryPoints",
        "Provide a different field name", "Custom.StoryPoints",
        "Yes, this is correct", "Yes, persist",
    ])
    with _MockExternalCalls(ado_sample=FAKE_ADO_SAMPLE_NO_STORY_POINTS) as mocks7:
        await run_feature_agent_discovery(
            TEST_PROJECT_ID + "-sp-corrected", "test-org", "Test Project", "cGxhY2Vob2xkZXI=",
            ask_human=scripted7, skills_root=skills_root,
        )
    assert mocks7.draft_body_calls[0]["context"]["discovery_caveats"] == []
    skill7 = load_skill(TEST_PROJECT_ID + "-sp-corrected", "feature-agent", skills_root=skills_root)
    assert "Discovery caveats" not in skill7.body
    assert skill7.frontmatter["fields"]["story_points_field"] == "Custom.StoryPoints"
    print("  PASS  correcting the field name instead of overriding records NO caveat — the "
          "distinction between 'PM fixed it' and 'PM knowingly proceeded past a real gap' is preserved")


async def run_status_report_agent_discovery_integration_tests(skills_root: str):
    print("\nrun_status_report_agent_discovery — scripted-conversation integration tests:")

    scripted = _ScriptedAskHuman(["Looks right", "*.pptx", "Yes, persist"])
    with _MockExternalCalls() as mocks:
        path = await run_status_report_agent_discovery(
            TEST_PROJECT_ID, "/fake/path/sample-report.pptx", ask_human=scripted, skills_root=skills_root,
        )
    assert path.exists()
    skill = load_skill(TEST_PROJECT_ID, "status-report-agent", skills_root=skills_root)
    assert skill.frontmatter == {"project_id": TEST_PROJECT_ID, "report_file_glob": "*.pptx"}
    assert skill.body == "Generated body text."
    assert len(mocks.draft_body_calls) == 1 and mocks.draft_body_calls[0]["skill_kind"] == "Status Report Agent"
    print("  PASS  happy path: real write_skill/load_skill round-trip produced the expected "
          "report_file_glob frontmatter")

    # 'Something's off' branch asks a follow-up question before the glob question
    scripted2 = _ScriptedAskHuman(["Something's off", "Team leads call it 'Wins' not 'Accomplishments'", "*.pptx", "Yes, persist"])
    with _MockExternalCalls() as mocks2:
        await run_status_report_agent_discovery(
            TEST_PROJECT_ID + "-notes", "/fake/path/sample-report.pptx", ask_human=scripted2, skills_root=skills_root,
        )
    assert mocks2.draft_body_calls[0]["context"]["pm_notes"] == "Team leads call it 'Wins' not 'Accomplishments'"
    print("  PASS  'Something's off' branch asks a follow-up and threads the PM's note into the body-drafting context")


async def main():
    print("Discovery Agent — test suite\n")
    run_pure_unit_tests()
    run_default_ask_human_tests()

    with tempfile.TemporaryDirectory() as skills_root:
        await run_feature_agent_discovery_integration_tests(skills_root)
        await run_status_report_agent_discovery_integration_tests(skills_root)

    print("\nAll pure unit and scripted-conversation integration tests passed.")
    print("\nGenuine tier 3 (a real interactive PM conversation against real ADO + a real report) "
          "is NOT automated — run agents/discovery_agent/discovery_agent.py directly yourself, see README.md.")


if __name__ == "__main__":
    asyncio.run(main())
