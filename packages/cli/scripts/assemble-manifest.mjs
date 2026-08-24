import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { supportedReleaseTargets } from "../src/platform.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(packageRoot, "../..");
const packageJson = JSON.parse(await readFile(path.join(packageRoot, "package.json"), "utf8"));
const requestedRoot = process.argv[2];
const fragmentsRoot = requestedRoot
  ? path.resolve(projectRoot, requestedRoot)
  : path.join(projectRoot, "release");
const repository = process.env.GITHUB_REPOSITORY || "waleed-khan13/socium";
const tag = process.env.RELEASE_TAG || `v${packageJson.version}`;
const serverUrl = process.env.GITHUB_SERVER_URL || "https://github.com";
const changelog = await readFile(path.join(projectRoot, "CHANGELOG.md"), "utf8");

function changelogNotes(version) {
  const heading = new RegExp(`^## ${version.replaceAll(".", "\\.")} - .+$`, "m");
  const match = heading.exec(changelog);
  if (!match) return "";
  const start = match.index + match[0].length;
  const next = changelog.indexOf("\n## ", start);
  return changelog.slice(start, next === -1 ? undefined : next).trim();
}

async function findFragments(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...(await findFragments(entryPath)));
    else if (/^socium-asset-.+\.json$/.test(entry.name)) found.push(entryPath);
  }
  return found;
}

const files = await findFragments(fragmentsRoot);
if (files.length === 0) throw new Error(`No release asset fragments found under ${fragmentsRoot}.`);

const assets = {};
for (const filePath of files) {
  const fragment = JSON.parse(await readFile(filePath, "utf8"));
  if (fragment.version !== packageJson.version) {
    throw new Error(`${filePath} contains version ${fragment.version}; expected ${packageJson.version}.`);
  }
  if (assets[fragment.target]) throw new Error(`Duplicate release target: ${fragment.target}.`);
  assets[fragment.target] = {
    url: `${serverUrl}/${repository}/releases/download/${tag}/${fragment.file}`,
    sha256: fragment.sha256,
  };
}
const requiredTargets = supportedReleaseTargets();
const missingTargets = requiredTargets.filter((target) => !assets[target]);
const unexpectedTargets = Object.keys(assets).filter((target) => !requiredTargets.includes(target));
if (missingTargets.length || unexpectedTargets.length) {
  throw new Error(
    `Release assets must match the supported platform matrix. Missing: ${missingTargets.join(", ") || "none"}; unexpected: ${unexpectedTargets.join(", ") || "none"}.`,
  );
}

const releaseNotes = process.env.SOCIUM_RELEASE_NOTES?.trim() || changelogNotes(packageJson.version);
if (!releaseNotes) throw new Error(`CHANGELOG.md has no release notes for ${packageJson.version}.`);

const manifest = {
  schemaVersion: 1,
  product: "socium",
  version: packageJson.version,
  publishedAt: new Date().toISOString(),
  releaseNotes,
  releaseNotesUrl: `${serverUrl}/${repository}/releases/tag/${tag}`,
  assets,
};
const outputPath = path.join(fragmentsRoot, "socium-manifest.json");
await writeFile(outputPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputPath} with ${Object.keys(assets).length} platform assets.`);
