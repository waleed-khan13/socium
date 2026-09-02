import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { runtimeLayout, startRuntime } from "./runtime.mjs";
import { sociumPaths } from "./paths.mjs";
import { relocateStorage } from "./storage.mjs";

function sleep(milliseconds) { return new Promise((resolve) => setTimeout(resolve, milliseconds)); }

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? Number(process.argv[index + 1]) : fallback;
  if (!Number.isInteger(value) || value < 1 || value > 65535) throw new Error(`${name} must be 1-65535.`);
  return value;
}

function stringArgument(name) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : "";
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

async function waitForProcessExit(pid, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      process.kill(pid, 0);
    } catch (error) {
      if (error?.code !== "EPERM") return;
    }
    await sleep(250);
  }
  throw new Error("Timed out waiting for Socium to close its database before the storage move.");
}

function launchWindowsTray(helper, dataDirectory) {
  const lock = path.join(dataDirectory, ".socium-runtime.json");
  const child = spawn(helper, ["tray", "--state-file", lock], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.once("error", () => {});
  child.unref();
}

async function main() {
  const paths = sociumPaths();
  const wantsTray = process.argv.includes("--tray");
  const webPort = argument("--port", 3000);
  const apiPort = argument("--api-port", 8000);
  if (process.argv[2] === "storage-move") {
    await waitForProcessExit(Number(stringArgument("--wait-pid")));
    await relocateStorage({
      paths,
      dataDirectory: stringArgument("--data-dir"),
      modelsDirectory: stringArgument("--models-dir"),
    });
  }
  let firstRun = true;
  while (true) {
    const run = startRuntime({
      paths,
      webPort,
      apiPort,
      shouldOpenBrowser: firstRun && !process.argv.includes("--no-open"),
      labsEnabled: process.argv.includes("--labs"),
      trayMode: wantsTray,
    });
    if (wantsTray && firstRun && process.platform === "win32") {
      for (let count = 0; count < 50; count += 1) {
        try {
          const installation = JSON.parse(await readFile(paths.installationFile, "utf8"));
          await readFile(path.join(installation.dataDirectory, ".socium-runtime.json"), "utf8");
          const helper = runtimeLayout(installation).nativeHelper;
          if (!helper) throw new Error("The Windows native helper is not available.");
          await readFile(helper);
          launchWindowsTray(helper, installation.dataDirectory);
          break;
        } catch { await sleep(100); }
      }
    }
    const result = await run;
    if (result.action !== "restart") break;
    firstRun = false;
    await sleep(1_000);
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
