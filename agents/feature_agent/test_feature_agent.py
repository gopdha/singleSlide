#!/usr/bin/env python3
"""
Structural + skill-loading checks always run. Request-construction validated
with a placeholder ANTHROPIC_API_KEY if set. A full live run needs a real
API key + real ADO org/PAT — see README.md.

Run with:
    python3 test_feature_agent.py
    ANTHROPIC_API_KEY=sk-ant-fake python3 test_feature_agent.py
    ANTHROPIC_API_KEY=... ADO_ORG=... ADO_PROJECT=... ADO_PAT_BASE64=... python3 test_feature_agent.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from feature_agent import FEATURE_SCHEMA, _build_entry_wiql, investigate_feature, list_committed_features  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from skill_loader import load_skill  # noqa: E402

SKILLS_ROOT = str(Path(__file__).parent.parent.parent / "skills")
TEST_PROJECT_ID = "ai-reports-demo"


async def main():
    print("Feature Agent (skill-driven) — test suite\n")

    print("Structural checks (no API/network call):")
    assert callable(investigate_feature)
    assert callable(list_committed_features)
    print("  PASS  investigate_feature and list_committed_features are importable and callable")

    required_fields = {"feature_id", "title", "short_description", "status_label", "progress_summary", "risk", "evidence"}
    assert required_fields.issubset(set(FEATURE_SCHEMA["properties"].keys()))
    assert FEATURE_SCHEMA["properties"]["status_label"]["enum"] == ["On Track", "At Risk", "Blocked", "Needs Human Review"]
    print("  PASS  FEATURE_SCHEMA has the agreed 4-level status taxonomy (including Needs Human Review)")

    print("\nSkill loading checks:")
    skill = load_skill(TEST_PROJECT_ID, "feature-agent", SKILLS_ROOT)
    assert skill.frontmatter["entry_criteria"]["filter_value"] == "Committed"
    assert "Story Points" in skill.body
    print("  PASS  example skill loads correctly (frontmatter + body)")

    wiql = _build_entry_wiql(skill.frontmatter["entry_criteria"], "AI Reports Demo")
    assert "Feature" in wiql and "Committed" in wiql and "CONTAINS" in wiql
    print("  PASS  WIQL correctly built from skill's entry_criteria")

    try:
        load_skill("nonexistent-project", "feature-agent", SKILLS_ROOT)
        print("  FAIL  expected FileNotFoundError for a project with no skill, got none")
        sys.exit(1)
    except FileNotFoundError:
        print("  PASS  missing skill fails loudly (no silent fallback to a default)")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nANTHROPIC_API_KEY not set — skipping request validation and live run.")
        print("Structural checks passed.")
        return

    org = os.environ.get("ADO_ORG")
    project = os.environ.get("ADO_PROJECT")
    pat_base64 = os.environ.get("ADO_PAT_BASE64")

    if not (org and project and pat_base64):
        print("\nANTHROPIC_API_KEY is set but ADO_ORG/ADO_PROJECT/ADO_PAT_BASE64 are not.")
        print("Running a request-construction check only (expects a clean failure at auth/network):\n")
        try:
            await investigate_feature(
                feature_id=99999, title="placeholder", org="placeholder-org", project="placeholder-project",
                pat_base64="cGxhY2Vob2xkZXI=", project_id=TEST_PROJECT_ID, skills_root=SKILLS_ROOT, model="claude-sonnet-5",
            )
            print("Unexpected: call succeeded against placeholder org — please double-check this result.")
        except RuntimeError as err:
            print(f"Got expected failure (this is success for a structural check): {err}")
            print("\nRequest construction validated. Structural checks passed.")
        return

    print(f"\nFull config detected — investigating real Committed Features in {org}/{project}...\n")
    features = await list_committed_features(org, project, pat_base64, TEST_PROJECT_ID, SKILLS_ROOT, debug=True)
    print(f"Found {len(features)} reportable item(s): {[f['title'] for f in features]}")
    if not features:
        print("No reportable items found — tag at least one Feature 'Committed' in ADO and retry.")
        return

    first = features[0]
    print(f"\nInvestigating #{first['id']} (\"{first['title']}\")...")
    result = await investigate_feature(first["id"], first["title"], org, project, pat_base64, TEST_PROJECT_ID, SKILLS_ROOT)
    print("\nResult:")
    for k, v in result.items():
        print(f"  {k}: {v}")

    assert result["status_label"] in ("On Track", "At Risk", "Blocked", "Needs Human Review")
    print("\nPASS  live Feature Agent investigation completed with a valid status label")


if __name__ == "__main__":
    asyncio.run(main())
