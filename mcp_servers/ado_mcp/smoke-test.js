#!/usr/bin/env node
/**
 * Smoke test for the official Azure DevOps MCP server (@azure-devops/mcp).
 * Run this against YOUR real ADO org after completing the setup steps in README.md.
 *
 * This must be run on a machine that can reach dev.azure.com — it will NOT
 * work from a network-restricted sandbox.
 *
 * Usage:
 *   export PERSONAL_ACCESS_TOKEN="<base64 value from encode-pat.js>"
 *   node smoke-test.js <your-ado-org-name>
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const org = process.argv[2];
if (!org) {
  console.error("Usage: node smoke-test.js <your-ado-org-name>");
  process.exit(1);
}
if (!process.env.PERSONAL_ACCESS_TOKEN) {
  console.error("Set PERSONAL_ACCESS_TOKEN first (see encode-pat.js).");
  process.exit(1);
}

async function main() {
  const transport = new StdioClientTransport({
    command: "npx",
    args: ["-y", "@azure-devops/mcp", org, "--authentication", "pat"],
    env: { ...process.env },
  });

  const client = new Client({ name: "ado-mcp-smoke-test", version: "1.0.0" });
  await client.connect(transport);

  const tools = await client.listTools();
  console.log(`\nConnected. Server exposes ${tools.tools.length} tools. First 10:`);
  console.log(tools.tools.slice(0, 10).map((t) => `  - ${t.name}`).join("\n"));

  // Try a basic, low-risk read call: list projects in the org.
  const listProjectsTool =
    tools.tools.find((t) => t.name === "core_list_projects") ||
    tools.tools.find((t) => /list.*project/i.test(t.name));
  if (listProjectsTool) {
    console.log(`\nCalling '${listProjectsTool.name}'...`);
    const result = await client.callTool({ name: listProjectsTool.name, arguments: {} });
    for (const block of result.content) {
      if (block.type === "text") console.log(block.text.slice(0, 2000));
    }
  } else {
    console.log("\nNo obvious 'list projects' tool found — inspect the full tool list above.");
  }

  await client.close();
  console.log("\nSmoke test complete.");
}

main().catch((err) => {
  console.error("Smoke test failed:", err);
  process.exit(1);
});
