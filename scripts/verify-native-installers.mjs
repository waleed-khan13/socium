import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import { nativeInstallerFileName, nativeInstallerTargets } from "./native-installer-names.mjs";

const projectRoot = process.cwd();
const releaseDirectory = path.join(projectRoot, "release");
const version = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8")).version;
const repository = process.env.GITHUB_REPOSITORY || "waleed-khan13/socium";
const serverUrl = process.env.GITHUB_SERVER_URL || "https://github.com";
const tag = process.env.RELEASE_TAG || `v${version}`;

async function sha256(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

const installers = {};
for (const target of nativeInstallerTargets) {
  const metadataPath = path.join(releaseDirectory, `socium-installer-${target}.json`);
  const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
  const expectedName = nativeInstallerFileName(version, target);
  if (metadata.target !== target || metadata.version !== version || metadata.file !== expectedName) {
    throw new Error(`${metadataPath} does not describe the expected installer.`);
  }
  const installerPath = path.join(releaseDirectory, expectedName);
  const details = await stat(installerPath);
  if (details.size < 1_000_000) throw new Error(`${expectedName} is unexpectedly small.`);
  if ((await sha256(installerPath)) !== metadata.sha256) throw new Error(`${expectedName} checksum does not match its build metadata.`);
  installers[target] = {
    url: `${serverUrl}/${repository}/releases/download/${tag}/${expectedName}`,
    sha256: metadata.sha256,
  };
}

const manifestPath = path.join(releaseDirectory, "socium-manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
if (manifest.product !== "socium" || manifest.version !== version) throw new Error("Release manifest does not match the installer matrix.");
manifest.installers = installers;
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Verified ${nativeInstallerTargets.length} dependency-free native installers for Socium ${version}.`);
