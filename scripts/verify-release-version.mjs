import { readFile } from "node:fs/promises";
import path from "node:path";

import { CLI_VERSION } from "../packages/cli/src/constants.mjs";

const projectRoot = process.cwd();
const readJson = async (filePath) => JSON.parse(await readFile(path.join(projectRoot, filePath), "utf8"));
const rootPackage = await readJson("package.json");
const cliPackage = await readJson("packages/cli/package.json");
const connectBrokerPackage = await readJson("packages/connect-broker/package.json");
const webRuntimePackage = await readJson("packaging/web-runtime/package.json");
const webRuntimeLock = await readJson("packaging/web-runtime/package-lock.json");
const backendProject = await readFile(path.join(projectRoot, "backend", "pyproject.toml"), "utf8");
const backendLock = await readFile(path.join(projectRoot, "backend", "uv.lock"), "utf8");
const backendInit = await readFile(path.join(projectRoot, "backend", "app", "__init__.py"), "utf8");
const nativeProject = await readFile(path.join(projectRoot, "native", "windows-helper", "Cargo.toml"), "utf8");
const nativeLock = await readFile(path.join(projectRoot, "native", "windows-helper", "Cargo.lock"), "utf8");
const changelog = await readFile(path.join(projectRoot, "CHANGELOG.md"), "utf8");
const backendVersion = backendProject.match(/^version = "([^"]+)"$/m)?.[1];
const backendLockVersion = backendLock.match(/\[\[package\]\]\r?\nname = "socium-api"\r?\nversion = "([^"]+)"/)?.[1];
const backendRuntimeVersion = backendInit.match(/^__version__ = "([^"]+)"$/m)?.[1];
const nativeVersion = nativeProject.match(/^version = "([^"]+)"$/m)?.[1];
const nativeLockVersion = nativeLock.match(/\[\[package\]\]\r?\nname = "socium-windows-helper"\r?\nversion = "([^"]+)"/)?.[1];
const versions = {
  root: rootPackage.version,
  cli: cliPackage.version,
  cliConstant: CLI_VERSION,
  connectBroker: connectBrokerPackage.version,
  webRuntime: webRuntimePackage.version,
  webRuntimeLock: webRuntimeLock.version,
  backend: backendVersion,
  backendLock: backendLockVersion,
  backendRuntime: backendRuntimeVersion,
  native: nativeVersion,
  nativeLock: nativeLockVersion,
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
const [major, minor] = expected.split(".");
const releaseContractPath = path.join(projectRoot, "docs", `V${major}_${minor}_RELEASE.md`);
const releaseContract = await readFile(releaseContractPath, "utf8");
if (!releaseContract.includes(`Release readiness: complete for v${expected}.`)) {
  throw new Error(`The v${major}.${minor} release contract is not marked ready for v${expected}.`);
}

const tag = process.env.RELEASE_TAG || process.argv[2];
if (tag && tag !== `v${expected}`) {
  throw new Error(`Release tag ${tag} does not match package version v${expected}.`);
}

console.log(`Release version ${expected} is consistent${tag ? ` with tag ${tag}` : ""}.`);
