# PPT MCP Server (internal, custom)

Implements `parse_slide(file_path)` per System Design Document Section 4.3.
Parses a team lead's weekly status PowerPoint (first slide) into structured
status data: accomplishments, planned next steps, risks/blockers, help
needed, any tables, and color-coded RAG cues from shape fills.

## Setup
```bash
cd ppt-mcp
pip install -r requirements.txt --break-system-packages
```

## Run standalone (stdio)
```bash
python3 server.py
```

## Test end-to-end (builds a real test fixture, calls the tool via MCP protocol)
```bash
python3 test_local.py
```

## Tool contract
```
parse_slide(file_path: str) -> {
  team_lead_id: str,
  sections: { accomplishments, planned_next, risks, help_needed },
  tables: [[[str]]],
  color_cues: [{ shape_id, shape_name, rgb, inferred_status }],
  parse_confidence: float,      // 0.0-1.0 — flag low values for PM review
  missing_sections: string[],
  slide_count_in_deck: int
}
```

## How section detection works
The parser looks for short text lines (<40 chars) matching keywords like
"Accomplishments", "Planned Next Steps", "Risks", or "Help Needed" and treats
everything until the next header as that section's body text. Color cues are
classified by nearest-neighbor distance to reference Red/Amber/Green swatches;
shapes with an unrelated fill color are ignored rather than mis-tagged.

## If your team leads' decks use different headers
Add your organization's actual phrasing to `SECTION_KEYWORDS` in `server.py`
(e.g. if leads write "Wins" instead of "Accomplishments", it's already there —
extend the list for anything not covered).

## Wiring into an MCP client (e.g. Claude Desktop config)
```json
{
  "mcpServers": {
    "ppt-teamlead": {
      "command": "python3",
      "args": ["/absolute/path/to/ppt-mcp/server.py"]
    }
  }
}
```
