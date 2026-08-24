import { readFile } from "node:fs/promises";
import path from "node:path";

import { CLI_VERSION } from "../packages/cli/src/constants.mjs";

const projectRoot = process.cwd();
const readJson = async (filePath) => JSON.parse(await readFile(path.join(projectRoot, filePath), "utf8"));
const rootPackage = await readJson("package.json");
const cliPackage = await readJson("packages/cli/package.json");
const webRuntimePackage = await readJson("packaging/web-runtime/package.json");
const backendProject = await readFile(path.join(projectRoot, "backend", "pyproject.toml"), "utf8");
const changelog = await readFile(path.join(projectRoot, "CHANGELOG.md"), "utf8");
const releaseContract = await readFile(path.join(projectRoot, "docs", "V1_1_RELEASE.md"), "utf8");
const backendVersion = backendProject.match(/^version = "([^"]+)"$/m)?.[1];
const versions = {
  root: rootPackage.version,
  cli: cliPackage.version,
  cliConstant: CLI_VERSION,
  webRuntime: webRuntimePackage.version,
  backend: backendVersion,
};
const expected = cliPackage.version;
const mismatches = Object.entries(versions).filter(([, version]) => version !== expected);
if (mismatches.length > 0) {
  throw new Error(
    `Release versions must match ${expected}: ${mismatches.map(([name, version]) => `${name}=${version}`).join(", ")}`,
  );
}
if (!new RegExp(`^## ${expected.replaceAll(".", "\\.")} - \\d{4}-\\d{2}-\\d{2}$`, "m").test(changelog)) {
  throw new Error(`CHANGELOG.md has no dated ${expected} release entry.`);
}
if (expected === "1.1.0" && !releaseContract.includes("11. [x] Pass release hardening and publish `v1.1.0`.")) {
  throw new Error("The v1.1 release contract is not marked complete.");
}

const tag = process.env.RELEASE_TAG || process.argv[2];
if (tag && tag !== `v${expected}`) {
  throw new Error(`Release tag ${tag} does not match package version v${expected}.`);
}

console.log(`Release version ${expected} is consistent${tag ? ` with tag ${tag}` : ""}.`);
