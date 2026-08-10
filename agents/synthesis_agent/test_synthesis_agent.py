#!/usr/bin/env python3
"""
Part A (merge_feature_enrichments) is pure — comprehensive unit tests, always run, no
credentials. Parts B/C (curate_report, write_executive_summary) follow the same 3-tier
pattern as every other agentic component: structural checks always run; request
construction validated with a placeholder ANTHROPIC_API_KEY; full live run needs a real
key (and, only for the full synthesize_report path, a real DATABASE_URL too — Parts B/C
alone need no DB, since prior_week is just a plain argument).

Run with:
    python3 test_synthesis_agent.py
    ANTHROPIC_API_KEY=sk-ant-fake python3 test_synthesis_agent.py
    ANTHROPIC_API_KEY=... python3 test_synthesis_agent.py                        # live B/C
    ANTHROPIC_API_KEY=... DATABASE_URL=... python3 test_synthesis_agent.py       # + live synthesize_report
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import synthesis_agent as sa  # noqa: E402
from synthesis_agent import (  # noqa: E402
    CURATE_REPORT_SCHEMA,
    RISK_FLOOR_LABELS,
    WRITE_SUMMARY_SCHEMA,
    curate_report,
    merge_feature_enrichments,
    synthesize_report,
    write_executive_summary,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
import mcp_client  # noqa: E402
from skill_loader import load_skill  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))
from rag_rollup import compute_rag_rollup  # noqa: E402

SKILLS_ROOT = str(Path(__file__).parent.parent.parent / "skills")
TEST_PROJECT_ID = "ai-reports-demo"


def _feature(feature_id: int, status_label: str, evidence: list[str], risk=None, **extra) -> dict:
    return {
        "feature_id": feature_id, "title": f"Feature {feature_id}", "short_description": "x",
        "status_label": status_label, "progress_summary": "y", "risk": risk, "evidence": evidence, **extra,
    }


def _enrichment(related_feature_id, match_confidence, excerpt, note="because") -> dict:
    return {
        "related_feature_id": related_feature_id,
        "related_feature_title_guess": f"Feature {related_feature_id}" if related_feature_id else "guess",
        "match_confidence": match_confidence, "excerpt": excerpt, "note": note,
    }


def run_part_a_tests():
    print("Part A (merge_feature_enrichments) — pure unit tests:")

    # High confidence, no overlap -> merged into evidence, risk filled (was null)
    features = [_feature(1, "At Risk", ["ADO comment: vendor sandbox unstable"], risk=None)]
    enrichments = [_enrichment(1, "high", "Vendor API has been down for three days")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["evidence"] == ["ADO comment: vendor sandbox unstable", "[Status report] Vendor API has been down for three days"]
    assert result[0]["risk"] == "Vendor API has been down for three days"
    print("  PASS  high-confidence, non-overlapping enrichment merges into evidence and fills empty risk")

    # Low confidence -> skipped entirely
    features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    enrichments = [_enrichment(1, "low", "some vague mention")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["evidence"] == ["comment A"] and result[0]["risk"] is None
    print("  PASS  low-confidence enrichment is skipped entirely")

    # related_feature_id null -> skipped
    features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    enrichments = [_enrichment(None, "high", "unattributable mention")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["evidence"] == ["comment A"]
    print("  PASS  enrichment with null related_feature_id is skipped (no title-guess matching)")

    # related_feature_id doesn't match any feature this week -> skipped, no crash
    features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    enrichments = [_enrichment(999, "high", "mentions a Feature not in this batch")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["evidence"] == ["comment A"]
    print("  PASS  enrichment referencing an unknown feature_id is skipped without error")

    # Overlapping excerpt -> skipped (redundant with existing ADO evidence)
    features = [_feature(1, "At Risk", ["Vendor sandbox has been unstable all week"], risk=None)]
    enrichments = [_enrichment(1, "high", "Vendor sandbox has been unstable all week long")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["evidence"] == ["Vendor sandbox has been unstable all week"]  # nothing appended
    print("  PASS  enrichment substantially overlapping existing evidence is skipped as redundant")

    # risk already set -> not overwritten, but evidence still appended
    features = [_feature(1, "Blocked", ["comment A"], risk="Existing known risk")]
    enrichments = [_enrichment(1, "high", "A completely different new detail")]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["risk"] == "Existing known risk"
    assert result[0]["evidence"] == ["comment A", "[Status report] A completely different new detail"]
    print("  PASS  non-null risk is never overwritten, even by a qualifying enrichment")

    # Multiple qualifying enrichments for the same feature: only the first fills risk
    features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    enrichments = [
        _enrichment(1, "high", "Vendor sandbox instability blocking QA"),
        _enrichment(1, "high", "Budget sign-off needed from finance by Friday"),
    ]
    result = merge_feature_enrichments(features, enrichments)
    assert result[0]["risk"] == "Vendor sandbox instability blocking QA"
    assert len(result[0]["evidence"]) == 3  # original + both appended
    print("  PASS  multiple qualifying enrichments: only the first (in input order) fills risk; both append to evidence")

    # Overlap is checked against the GROWING working evidence, not just the original
    features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    enrichments = [
        _enrichment(1, "high", "The vendor sandbox has been down since Tuesday"),
        _enrichment(1, "high", "Vendor sandbox down since Tuesday, still unresolved"),
    ]
    result = merge_feature_enrichments(features, enrichments)
    assert len(result[0]["evidence"]) == 2, "second near-duplicate enrichment should be skipped against the first, already-merged one"
    print("  PASS  overlap check compares against evidence merged earlier in the same call, not just the original list")

    # Input is not mutated
    original_features = [_feature(1, "At Risk", ["comment A"], risk=None)]
    original_evidence_id = id(original_features[0]["evidence"])
    merge_feature_enrichments(original_features, [_enrichment(1, "high", "new detail")])
    assert original_features[0]["evidence"] == ["comment A"], "input features must not be mutated"
    assert id(original_features[0]["evidence"]) == original_evidence_id
    print("  PASS  input features list and dicts are not mutated — a new list is returned")

    # Extra fields pass through unchanged
    features = [_feature(1, "On Track", ["comment A"], risk=None, short_description="A real description")]
    result = merge_feature_enrichments(features, [])
    assert result[0]["short_description"] == "A real description" and result[0]["title"] == "Feature 1"
    print("  PASS  fields other than evidence/risk pass through unchanged")


def run_structural_checks():
    print("\nStructural checks (no API/network call):")
    assert callable(curate_report) and callable(write_executive_summary) and callable(synthesize_report)
    print("  PASS  curate_report, write_executive_summary, and synthesize_report are importable and callable")

    assert RISK_FLOOR_LABELS == {"Blocked", "At Risk", "Needs Human Review"}
    print("  PASS  RISK_FLOOR_LABELS includes Needs Human Review (extended per docs/DECISION_LOG.md)")

    curated_feature_props = CURATE_REPORT_SCHEMA["properties"]["curated_features"]["items"]["properties"]
    assert curated_feature_props["status_label"]["enum"] == ["On Track", "At Risk", "Blocked", "Needs Human Review"]
    assert set(CURATE_REPORT_SCHEMA["required"]) == {"deduped_initiatives", "curated_features", "curated_initiatives"}
    print("  PASS  CURATE_REPORT_SCHEMA has all 3 required keys (deduped_initiatives included) and the full taxonomy")

    assert set(WRITE_SUMMARY_SCHEMA["required"]) == {"executive_summary", "trend_line"}
    print("  PASS  WRITE_SUMMARY_SCHEMA requires both executive_summary and trend_line")

    skill = load_skill(TEST_PROJECT_ID, "synthesis-agent", SKILLS_ROOT)
    assert skill.body.strip()
    print("  PASS  example synthesis-agent skill loads correctly")

    try:
        load_skill("nonexistent-project", "synthesis-agent", SKILLS_ROOT)
        print("  FAIL  expected FileNotFoundError for a project with no skill, got none")
        sys.exit(1)
    except FileNotFoundError:
        print("  PASS  missing skill fails loudly (no silent fallback to a default)")


async def run_risk_floor_violation_test():
    """Proves the safety net actually catches something — same instinct as feature_agent's
    per-item failure isolation test. Mocks _run_agentic_call to simulate the model
    mishandling the floor rule (dropping a Blocked Feature), then confirms curate_report's
    own validation code raises, not the model's good behavior. No credentials needed —
    the real Anthropic call never happens."""
    print("\nRisk-floor safety-net test (no credentials needed — the agentic call itself is mocked):")

    features = [
        _feature(1, "Blocked", ["comment A"]),
        _feature(2, "Needs Human Review", ["comment B"]),
        _feature(3, "On Track", ["comment C"]),
    ]
    rag_rollup_result = compute_rag_rollup(features)

    async def _bad_agentic_call(prompt, system_prompt, schema, model, max_turns, caller_name):
        # Simulates the model dropping BOTH a Blocked and a Needs Human Review Feature —
        # exactly the violation the floor exists to catch.
        return {
            "deduped_initiatives": [],
            "curated_features": [
                {"feature_id": 3, "title": "Feature 3", "status_label": "On Track", "display_text": "on track"},
            ],
            "curated_initiatives": [],
        }

    original_call = sa._run_agentic_call
    sa._run_agentic_call = _bad_agentic_call
    try:
        try:
            await curate_report(features, [], rag_rollup_result, None, TEST_PROJECT_ID, SKILLS_ROOT)
            print("  FAIL  expected RuntimeError when the (mocked) agent dropped Blocked/NHR Features, got none")
            sys.exit(1)
        except RuntimeError as err:
            assert "risk floor" in str(err)
            assert "1" in str(err) and "2" in str(err), "error should name both missing feature_ids (1 and 2)"
            print(f"  PASS  risk-floor validation fires correctly when the agent violates it: {err}")
    finally:
        sa._run_agentic_call = original_call


async def run_live_checks(database_url: str | None):
    print("\nFull config detected — running live Part B/C checks against the real Anthropic API...\n")
    print("Using: a synthetic-but-realistic 'Build Agentic Dashboard' Feature (id 101) modeled on "
          "the real one used in this project's earlier live runs, plus the ACTUAL potential_enrichments "
          "and Other Initiatives produced by status_report_agent's real live run earlier in this "
          "project (Priya Nair's week-32 report) — not fabricated from scratch. feature_agent itself "
          "was not re-run live here (no ADO credentials in this session); its status/evidence fields "
          "below are realistic synthetic, not a fresh ADO pull.\n")

    features = [
        _feature(101, "At Risk", ["ADO: 3 of 5 story points remaining, demo scheduled for Friday"], risk=None,
                  title="Build Agentic Dashboard", short_description="Agentic dashboard for weekly reports",
                  progress_summary="Core screens in progress; on track for Friday demo but behind original estimate."),
        _feature(205, "Blocked", ["ADO comment: waiting on legal sign-off for vendor data-sharing addendum"], risk="Legal sign-off blocking vendor integration",
                  title="Vendor Integration Overhaul", short_description="Overhaul of the vendor data integration layer",
                  progress_summary="Implementation complete; cannot proceed to testing without signed addendum."),
        _feature(310, "On Track", ["ADO: all 4 planned stories closed this sprint"],
                  title="Internal Tooling Cleanup", short_description="Cleanup of internal dev tooling",
                  progress_summary="Sprint goals met on schedule."),
        _feature(412, "Needs Human Review", ["No comments or revision history found on this item"],
                  title="Legacy Auth Migration", short_description="Migrating legacy auth to the new identity provider",
                  progress_summary="No evidence found to support a confident status either way."),
    ]

    # The ACTUAL potential_enrichments produced by status_report_agent's real live run
    # (Priya Nair's week-32 report, earlier in this project) — feature_id updated from the
    # synthetic 101 placeholder used then to match this run's fixture (same id, coincidentally).
    enrichments = [
        {"related_feature_id": 101, "related_feature_title_guess": "Build Agentic Dashboard", "match_confidence": "high",
         "excerpt": "Made solid progress on the Build Agentic Dashboard effort — most of the core screens are done.",
         "note": "Explicitly names the 'Build Agentic Dashboard' effort and reports progress on core screens."},
        {"related_feature_id": 101, "related_feature_title_guess": "Build Agentic Dashboard", "match_confidence": "high",
         "excerpt": "Continue tightening up dashboard performance ahead of the demo.",
         "note": "Refers to 'dashboard' performance work as a next step, following directly from the same "
                 "report's explicit mention of the Build Agentic Dashboard effort in accomplishments."},
        {"related_feature_id": 101, "related_feature_title_guess": "Build Agentic Dashboard", "match_confidence": "low",
         "excerpt": "Some flakiness this week in one of our automation pipelines — not yet clear if it's tied "
                    "to the dashboard work or a separate issue.",
         "note": "Report itself is uncertain whether this risk is connected to the dashboard effort."},
    ]

    # The ACTUAL Other Initiatives from that same real live run, plus a second team lead's
    # differently-phrased mention of the same vendor-renewal initiative, so Part B has real
    # cross-report dedup work to do (not just a single-source passthrough).
    initiatives = [
        {"title": "Vendor Contract Renewal", "narrative_summary": "The team wrapped up paperwork for a vendor contract renewal this week.",
         "evidence": ["Wrapped up the vendor contract renewal paperwork this week."]},
        {"title": "Vendor contract renewal", "narrative_summary": "Finished the renewal paperwork with our vendor this week.",
         "evidence": ["Renewal paperwork with the vendor was completed this week."]},
        {"title": "Team Offsite Planning", "narrative_summary": "The team is requesting budget sign-off to plan an offsite for next quarter.",
         "evidence": ["Need budget sign-off for the team offsite next quarter."]},
    ]

    merged_features = merge_feature_enrichments(features, enrichments)
    print("Part A output (merge_feature_enrichments) — Feature 101 after merge:")
    print(json.dumps(next(f for f in merged_features if f["feature_id"] == 101), indent=2))
    assert len(merged_features[0]["evidence"]) == 3, "1 original + 2 high-confidence enrichments (the low-confidence one must be excluded)"
    assert merged_features[0]["risk"] == "Made solid progress on the Build Agentic Dashboard effort — most of the core screens are done."
    print("\nPASS  Part A merged both high-confidence enrichments, correctly excluded the low-confidence one, "
          "and filled the previously-null risk field verbatim\n")

    rag_rollup_result = compute_rag_rollup(merged_features)
    assert rag_rollup_result["rag_status"] == "Red"  # Feature 205 is Blocked
    print(f"rag_rollup_result: {json.dumps(rag_rollup_result, indent=2)}\n")

    curation = await curate_report(merged_features, initiatives, rag_rollup_result, None, TEST_PROJECT_ID, SKILLS_ROOT)
    print("=" * 70)
    print("Part B — curate_report FULL RAW OUTPUT:")
    print("=" * 70)
    print(json.dumps(curation, indent=2))

    curated_ids = {f["feature_id"] for f in curation["curated_features"]}
    assert {101, 205, 412}.issubset(curated_ids), "At Risk/Blocked/Needs Human Review must all survive curation"
    assert len(curation["deduped_initiatives"]) <= len(initiatives), "dedup should not increase the initiative count"
    print(f"\nPASS  curate_report honored the risk floor (feature_ids {sorted(curated_ids)} present, "
          f"101/205/412 all required) and deduped_initiatives ({len(curation['deduped_initiatives'])}) "
          f"<= raw initiatives ({len(initiatives)})")

    narrative = await write_executive_summary(
        curation["curated_features"], curation["curated_initiatives"], rag_rollup_result, None, TEST_PROJECT_ID, SKILLS_ROOT,
    )
    print("\n" + "=" * 70)
    print("Part C — write_executive_summary FULL RAW OUTPUT:")
    print("=" * 70)
    print(json.dumps(narrative, indent=2))
    assert narrative["executive_summary"].strip()
    assert narrative["trend_line"] == "", "trend_line must be empty when prior_week is null"
    print("\nPASS  write_executive_summary produced a non-empty summary and an empty trend_line with no prior_week")

    if not database_url:
        print("\nDATABASE_URL not set — skipping the full synthesize_report live path (needs Archive too).")
        return

    print("\n" + "=" * 70)
    print("DATABASE_URL also set — running the full synthesize_report path against real Archive,")
    print("with call-counter instrumentation on get_prior_week_report:")
    print("=" * 70 + "\n")

    call_counts = {"get_prior_week_report": 0}
    original_client_call = mcp_client._McpClient.call

    async def _counting_call(self, tool_name, arguments):
        if tool_name == "get_prior_week_report":
            call_counts["get_prior_week_report"] += 1
        return await original_client_call(self, tool_name, arguments)

    mcp_client._McpClient.call = _counting_call
    try:
        report = await synthesize_report(
            TEST_PROJECT_ID, "2026-08-16", features, enrichments, initiatives, database_url, SKILLS_ROOT, debug=True,
        )
    finally:
        mcp_client._McpClient.call = original_client_call

    print("\n" + "=" * 70)
    print("synthesize_report FULL RAW OUTPUT:")
    print("=" * 70)
    print(json.dumps(report, indent=2))

    expected_keys = {"project_id", "week_of", "rag_status", "executive_summary", "trend_line",
                      "curated_features", "curated_initiatives", "features", "initiatives", "prior_week"}
    assert set(report.keys()) == expected_keys
    print(f"\nPASS  synthesize_report returned every expected key, end to end")

    assert call_counts["get_prior_week_report"] == 1, \
        f"expected get_prior_week_report called exactly once, got {call_counts['get_prior_week_report']}"
    print(f"PASS  get_prior_week_report was called exactly {call_counts['get_prior_week_report']} time "
          f"across the whole synthesize_report run (not once per Part)")


async def main():
    print("Synthesis Agent — test suite\n")
    run_part_a_tests()
    run_structural_checks()
    await run_risk_floor_violation_test()  # no credentials needed — the agentic call is mocked

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nANTHROPIC_API_KEY not set — skipping request validation and live checks.")
        print("Part A, structural, and risk-floor safety-net checks passed.")
        return

    database_url = os.environ.get("DATABASE_URL")
    # Distinguish a placeholder key from a real one the same way every other agent does:
    # a real request-construction check needs *a* key, but only a genuinely invalid one
    # proves construction is correct without needing real credentials for the live path.
    print("\nRunning a request-construction check (expects a clean failure at Anthropic auth):\n")
    try:
        await curate_report(
            [_feature(1, "On Track", ["x"])], [], compute_rag_rollup([_feature(1, "On Track", ["x"])]),
            None, TEST_PROJECT_ID, SKILLS_ROOT, model="claude-sonnet-5",
        )
        print("Unexpected: call succeeded — if this is a real key, proceeding to the full live run below.\n")
        await run_live_checks(database_url)
    except RuntimeError as err:
        if "invalid ANTHROPIC_API_KEY" in str(err):
            print(f"Got expected failure (this is success for a structural check): {err}")
            print("\nRequest construction validated. Part A and structural checks passed.")
        else:
            raise


if __name__ == "__main__":
    asyncio.run(main())
