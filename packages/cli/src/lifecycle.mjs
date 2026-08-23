import { spawn } from "node:child_process";
import { rm, stat } from "node:fs/promises";
import path from "node:path";
import net from "node:net";

import { createBackup, restoreBackup } from "./backup.mjs";
import { installRelease } from "./installation.mjs";
import { readJsonSource, validateManifest } from "./manifest.mjs";
import { releaseTarget } from "./platform.mjs";
import { sociumPaths } from "./paths.mjs";
import { runtimeLayout } from "./runtime.mjs";
import { loadInstallation, writeJsonAtomically } from "./state.mjs";

function versionParts(value) {
  const match = String(value).match(/^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
  if (!match) throw new Error(`Invalid release version: ${value}`);
  return match.slice(1).map(Number);
}

export function compareVersions(left, right) {
  const a = versionParts(left);
  const b = versionParts(right);
  for (let index = 0; index < 3; index += 1) if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  return 0;
}

export async function checkForUpdate({ manifestSource, paths = sociumPaths(), target = releaseTarget() } = {}) {
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed.");
  const manifest = await readJsonSource(manifestSource || installation.manifestSource);
  validateManifest(manifest, target);
  return {
    currentVersion: installation.version,
    latestVersion: manifest.version,
    updateAvailable: compareVersions(installation.version, manifest.version) < 0,
    publishedAt: manifest.publishedAt || null,
    releaseNotes: typeof manifest.releaseNotes === "string" ? manifest.releaseNotes : "",
    releaseNotesUrl: typeof manifest.releaseNotesUrl === "string" ? manifest.releaseNotesUrl : null,
  };
}

async function waitForProcess(pid, timeoutMs = 60_000) {
  if (!pid) return;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { process.kill(pid, 0); } catch { return; }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Socium did not stop within ${Math.ceil(timeoutMs / 1000)} seconds.`);
}

async function reservePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port: 0 }, resolve);
  });
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function verifyMigration(installation, timeoutMs = 90_000) {
  const port = await reservePort();
  const layout = runtimeLayout(installation);
  const child = spawn(layout.apiExecutable, ["--host", "127.0.0.1", "--port", String(port)], {
    cwd: installation.runtimePath,
    windowsHide: true,
    stdio: "ignore",
    env: {
      ...process.env,
      SOCIUM_API_HOST: "127.0.0.1",
      SOCIUM_API_PORT: String(port),
      SOCIUM_DATA_DIR: installation.dataDirectory,
      SOCIUM_MODELS_DIR: installation.modelsDirectory,
      SOCIUM_RUNTIME_DIR: installation.runtimePath,
      SOCIUM_STORAGE_REQUIRE_MARKER: "1",
      SOCIUM_AUTO_UPDATE_CHECKS: "0",
      SOCIUM_MIGRATION_CHECK: "1",
    },
  });
  const deadline = Date.now() + timeoutMs;
  try {
    while (Date.now() < deadline) {
      if (child.exitCode !== null) throw new Error("The updated API exited during its migration check.");
      try {
        const response = await fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(1_500) });
        if (response.ok) return;
      } catch {}
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
    throw new Error("The updated API did not become healthy after migration.");
  } finally {
    if (child.exitCode === null) {
      if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { windowsHide: true, stdio: "ignore" });
      else child.kill("SIGTERM");
    }
  }
}

export async function applyUpdate({ manifestSource, paths = sociumPaths(), target = releaseTarget(), force = false, waitPid, onDownloadProgress, log = console.log } = {}) {
  await waitForProcess(waitPid);
  const previous = await loadInstallation(paths);
  if (!previous) throw new Error("Socium is not installed.");
  const backup = await createBackup({ paths, reason: "pre-update", log });
  try {
    const installed = await installRelease({ manifestSource: manifestSource || previous.manifestSource, paths, target, force, backupPath: backup.path, onDownloadProgress, log });
    await verifyMigration(installed);
    await rm(path.join(installed.dataDirectory, ".updates"), { recursive: true, force: true });
    log("Update migration and health checks passed.");
    return installed;
  } catch (error) {
    const current = await loadInstallation(paths);
    if (current?.previousRelease?.runtimePath) {
      await rollbackRelease({ paths, log });
      log("Update failed; Socium restored the previous runtime and verified data backup.");
    }
    throw error;
  }
}

export async function rollbackRelease({ paths = sociumPaths(), log = console.log } = {}) {
  const installation = await loadInstallation(paths);
  if (!installation?.previousRelease?.runtimePath) throw new Error("No previous Socium release is available for rollback.");
  try { await stat(installation.previousRelease.runtimePath); } catch { throw new Error("The previous runtime is no longer available."); }
  if (installation.previousRelease.backupPath) await restoreBackup({ backupPath: installation.previousRelease.backupPath, paths, log });
  const current = { version: installation.version, target: installation.target, runtimePath: installation.runtimePath, backupPath: null };
  const rolledBack = {
    ...installation,
    version: installation.previousRelease.version,
    target: installation.previousRelease.target,
    runtimePath: installation.previousRelease.runtimePath,
    installedAt: new Date().toISOString(),
    previousRelease: current,
  };
  await writeJsonAtomically(paths.installationFile, rolledBack);
  log(`Rolled back to Socium ${rolledBack.version}.`);
  return rolledBack;
}
