import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { main } from "../packages/cli/src/cli.mjs";
import { releaseTarget } from "../packages/cli/src/platform.mjs";

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
  console.log(
    JSON.stringify(
      {
        ok: true,
        target,
        version: health.version,
        install: "checksummed",
        doctor: "passed",
        runtime: `http://127.0.0.1:${webPort}`,
      },
      null,
      2,
    ),
  );
} finally {
  if (runtime) await terminateProcessTree(runtime);
  await main(["uninstall", "--yes", "--purge-data"], { log() {}, error() {} });
  if (previousHome === undefined) delete process.env.SOCIUM_HOME;
  else process.env.SOCIUM_HOME = previousHome;
  await rm(testRoot, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
}
