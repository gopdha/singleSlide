import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "core"))
from orchestrator import run_pipeline

WEEK_OF = "2026-08-11"
REPORTS_DIR = "reports/singleslide"


async def main():
    required_vars = ["ADO_ORG", "ADO_PROJECT", "ADO_PAT_BASE64", "DATABASE_URL", "ANTHROPIC_API_KEY"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"Missing required env var(s): {', '.join(missing)}")
        sys.exit(1)

    result = await run_pipeline(
        project_id="singleslide",
        name="SingleSlide",
        week_of=WEEK_OF,
        ado_org=os.environ["ADO_ORG"],
        ado_project=os.environ["ADO_PROJECT"],
        ado_pat_base64=os.environ["ADO_PAT_BASE64"],
        reports_dir=REPORTS_DIR,
        database_url=os.environ["DATABASE_URL"],
        debug=True,
    )
    print(json.dumps(result, indent=2))


asyncio.run(main())
