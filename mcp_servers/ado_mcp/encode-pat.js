#!/usr/bin/env node
/**
 * Encodes an Azure DevOps PAT into the base64 "<email>:<pat>" format
 * required by @azure-devops/mcp's --authentication pat mode.
 * Usage: node encode-pat.js <your-raw-pat>
 */
const pat = process.argv[2];
if (!pat) {
  console.error("Usage: node encode-pat.js <your-raw-pat>");
  process.exit(1);
}
const encoded = Buffer.from(`user:${pat}`).toString("base64");
console.log("\nPERSONAL_ACCESS_TOKEN value (base64-encoded):\n");
console.log(encoded);
console.log("\nSet it with:\n  export PERSONAL_ACCESS_TOKEN=\"" + encoded + "\"\n");
