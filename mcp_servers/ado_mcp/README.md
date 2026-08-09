# Azure DevOps MCP Server (external, official Microsoft package)

This wraps Microsoft's official `@azure-devops/mcp` package — no custom code,
just configuration, matching the PRD's "external MCP tools" category.

**Verified so far (from this environment):** the package installs cleanly,
starts correctly, completes a real MCP handshake, and exposes 40 real tools
(`core_list_projects`, `work`, `pipelines_build`, `wit_*` work-item tools,
etc.). The actual API calls to `dev.azure.com` could not be tested from this
sandbox (network egress here is restricted to package registries) — you'll
run the final smoke test yourself, on your own machine, against your real org.

## Steps to complete on your end

### 1. Create a free Azure DevOps org + real work items
- Sign up at https://dev.azure.com (free tier).
- Create one project.
- Add 2 sprints and ~15–20 real work items (mix of Tasks/Bugs, a couple marked Blocked) through the UI.

### 2. Generate a read-only PAT
- In your ADO org: User Settings → Personal Access Tokens → New Token.
- Scope: **Work Items (Read)** only.
- Copy the raw token — you won't see it again.

### 3. Encode the PAT
```bash
cd ado-mcp
node encode-pat.js "<your-raw-pat>"
```
Copy the printed base64 value.

### 4. Run the smoke test against your real org
```bash
export PERSONAL_ACCESS_TOKEN="<base64 value from step 3>"
npm test -- <your-ado-org-name>
# equivalent to: node smoke-test.js <your-ado-org-name>
```
Expected output: the tool list (40 tools), followed by your real projects
returned by `core_list_projects`.

### 5. Wire it into your MCP client
Copy `mcp-client-config.example.json` into your MCP client's config
(e.g. Claude Desktop's `claude_desktop_config.json`, or a Claude Code
`.mcp.json`), filling in your org name and the base64 PAT:
```json
{
  "mcpServers": {
    "ado": {
      "command": "npx",
      "args": ["-y", "@azure-devops/mcp", "<YOUR_ADO_ORG_NAME>", "--authentication", "pat"],
      "env": { "PERSONAL_ACCESS_TOKEN": "<base64 value>" }
    }
  }
}
```

## Tools you'll use for this project (of the 40 available)
Per the System Design Document's MCP contracts, the ADO Agent primarily needs:
- `core_list_projects` — confirm connectivity / pick the target project
- `wit_*` work item tools — pull work items, states, and sprint data (exact
  tool names are visible once you run the smoke test — the package's tool
  surface is broader than the PRD's illustrative `get_work_items` /
  `get_sprint_status` / `get_burndown` signatures, so the ADO Agent's prompt
  should be pointed at the real tool names from your `listTools()` output)
- `work` domain tools — sprint/iteration status

## Files in this folder
- `encode-pat.js` — converts your raw PAT into the required base64 format
- `smoke-test.js` — connects to the real server and calls a real tool
- `mcp-client-config.example.json` — config template for an MCP client
- `package.json` — run `npm install` first
