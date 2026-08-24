import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { main } from "../packages/cli/src/cli.mjs";
import { loadInstallation } from "../packages/cli/src/installation.mjs";
import { autostartStatus, installNativeIntegration, removeNativeIntegration } from "../packages/cli/src/native-integration.mjs";
import { sociumPaths } from "../packages/cli/src/paths.mjs";
import { releaseTarget } from "../packages/cli/src/platform.mjs";
import { uninstall } from "../packages/cli/src/uninstall.mjs";

const projectRoot = process.cwd();
const target = process.env.SOCIUM_RELEASE_TARGET || releaseTarget();
const fragmentPath = path.join(projectRoot, "release", `socium-asset-${target}.json`);
const fragment = JSON.parse(await readFile(fragmentPath, "utf8"));
const archivePath = path.join(projectRoot, "release", fragment.file);
const testRoot = await mkdtemp(path.join(os.tmpdir(), "socium-cli-bundle-"));
const manifestPath = path.join(testRoot, "manifest.json");
const webPort = Number(process.env.SOCIUM_CLI_SMOKE_WEB_PORT || "8299");
const apiPort = Number(process.env.SOCIUM_CLI_SMOKE_API_PORT || "8298");
const previousHome = process.env.SOCIUM_HOME;

await writeFile(
  manifestPath,
  JSON.stringify({
    schemaVersion: 1,
    product: "socium",
    version: fragment.version,
    assets: {
      [target]: { url: pathToFileURL(archivePath).toString(), sha256: fragment.sha256 },
    },
  }),
  "utf8",
);
process.env.SOCIUM_HOME = path.join(testRoot, "home");
const paths = sociumPaths();
const nativeHome = path.join(testRoot, "native-home");
const nativeEnvironment = {
  ...process.env,
  APPDATA: path.join(nativeHome, "AppData", "Roaming"),
  OneDrive: path.join(nativeHome, "OneDrive"),
  XDG_CONFIG_HOME: path.join(nativeHome, ".config"),
};

async function terminateProcessTree(child) {
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const terminator = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        stdio: "ignore",
        windowsHide: true,
      });
      terminator.once("error", () => {
        child.kill();
        resolve();
      });
      terminator.once("exit", resolve);
    });
  } else {
    child.kill("SIGTERM");
  }
}

let runtime;
try {
  const installCode = await main(["onboard", "--manifest", manifestPath, "--install-only"]);
  if (installCode !== 0) throw new Error(`CLI install smoke returned ${installCode}.`);
  const doctorCode = await main(["doctor"]);
  if (doctorCode !== 0) throw new Error(`CLI doctor smoke returned ${doctorCode}.`);
  const installation = await loadInstallation(paths);
  await installNativeIntegration({
    paths,
    shortcuts: true,
    autostart: true,
    environment: nativeEnvironment,
    homeDirectory: nativeHome,
  });
  if (!(await autostartStatus({ environment: nativeEnvironment, homeDirectory: nativeHome })).enabled) {
    throw new Error("Native autostart was not enabled in the disposable profile.");
  }
  const durableFile = path.join(installation.dataDirectory, "release-smoke.json");
  await writeFile(durableFile, JSON.stringify({ value: "before-update" }), "utf8");

  runtime = spawn(
    process.platform === "win32"
      ? path.join(process.env.SOCIUM_HOME, "runtimes", fragment.version, target, "bin", "node.exe")
      : path.join(process.env.SOCIUM_HOME, "runtimes", fragment.version, target, "bin", "node"),
    [
      path.join(process.env.SOCIUM_HOME, "runtimes", fragment.version, target, "controller", "controller.mjs"),
      "--no-open",
      "--port",
      String(webPort),
      "--api-port",
      String(apiPort),
    ],
    {
      cwd: projectRoot,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );
  let stderr = "";
  runtime.stderr.setEncoding("utf8");
  runtime.stderr.on("data", (chunk) => {
    stderr += chunk;
  });

  const deadline = Date.now() + 90_000;
  let health;
  while (Date.now() < deadline) {
    if (runtime.exitCode !== null) throw new Error(`CLI runtime exited with ${runtime.exitCode}:\n${stderr}`);
    try {
      const response = await fetch(`http://127.0.0.1:${webPort}/api/health`, {
        cache: "no-store",
        signal: AbortSignal.timeout(1_500),
      });
      if (response.ok) {
        health = await response.json();
        break;
      }
    } catch {
      // The one-file API and standalone web server are still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  if (!health || health.service !== "socium-api") {
    throw new Error(`Installed CLI runtime did not become healthy:\n${stderr}`);
  }

  const runtimeLock = JSON.parse(await readFile(path.join(installation.dataDirectory, ".socium-runtime.json"), "utf8"));
  const statusResponse = await fetch(`http://127.0.0.1:${runtimeLock.controlPort}/status`, {
    headers: { Authorization: `Bearer ${runtimeLock.controlToken}` },
    signal: AbortSignal.timeout(5_000),
  });
  if (!statusResponse.ok || (await statusResponse.json()).version !== fragment.version) {
    throw new Error("The native controller status check failed.");
  }
  const stopResponse = await fetch(`http://127.0.0.1:${runtimeLock.controlPort}/stop`, {
    method: "POST",
    headers: { Authorization: `Bearer ${runtimeLock.controlToken}` },
    signal: AbortSignal.timeout(5_000),
  });
  if (!stopResponse.ok) throw new Error("The native controller did not accept a stop request.");
  if (runtime.exitCode === null) {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("The native controller did not stop.")), 30_000);
      runtime.once("exit", () => {
        clearTimeout(timeout);
        resolve();
      });
    });
  }
  runtime = undefined;

  const updateCode = await main(["update", "--manifest", manifestPath, "--force"], { output: { isTTY: false }, log() {} });
  if (updateCode !== 0 || !(await loadInstallation(paths)).previousRelease) {
    throw new Error("The native update smoke did not retain a rollback runtime.");
  }
  await writeFile(durableFile, JSON.stringify({ value: "after-update" }), "utf8");
  const rollbackCode = await main(["rollback"], { log() {} });
  if (rollbackCode !== 0 || JSON.parse(await readFile(durableFile, "utf8")).value !== "before-update") {
    throw new Error("Rollback did not restore the pre-update durable snapshot.");
  }

  await removeNativeIntegration({ environment: nativeEnvironment, homeDirectory: nativeHome });
  const uninstallResult = await uninstall({ paths, confirmed: true });
  if (!uninstallResult.preservedData || JSON.parse(await readFile(durableFile, "utf8")).value !== "before-update") {
    throw new Error("Normal uninstall did not preserve durable data.");
  }
  console.log(
    JSON.stringify(
      {
        ok: true,
        target,
        version: health.version,
        install: "checksummed",
        doctor: "passed",
        autostart: "passed",
        controller: "passed",
        updateRollback: "passed",
        uninstallDataPreservation: "passed",
        runtime: `http://127.0.0.1:${webPort}`,
      },
      null,
      2,
    ),
  );
} finally {
  if (runtime) await terminateProcessTree(runtime);
  await removeNativeIntegration({ environment: nativeEnvironment, homeDirectory: nativeHome }).catch(() => undefined);
  await uninstall({ paths, confirmed: true, purgeData: true }).catch(() => undefined);
  if (previousHome === undefined) delete process.env.SOCIUM_HOME;
  else process.env.SOCIUM_HOME = previousHome;
  await rm(testRoot, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
}
