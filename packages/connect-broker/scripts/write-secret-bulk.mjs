import { writeFile } from "node:fs/promises";
import path from "node:path";

const required = [
  "HANDOFF_ENCRYPTION_KEY",
  "SLACK_CLIENT_ID",
  "SLACK_CLIENT_SECRET",
  "SLACK_SIGNING_SECRET",
  "LINKEDIN_CLIENT_ID",
  "LINKEDIN_CLIENT_SECRET",
];
const missing = required.filter((name) => !process.env[name]?.trim());
if (missing.length) throw new Error(`Missing deployment secrets: ${missing.join(", ")}`);

const target = path.resolve(process.cwd(), ".production.secrets.json");
await writeFile(
  target,
  `${JSON.stringify(Object.fromEntries(required.map((name) => [name, process.env[name]])), null, 2)}\n`,
  { encoding: "utf8", mode: 0o600 },
);
console.log(`Prepared ${required.length} broker secrets for Wrangler.`);
