import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const projectRoot = process.cwd();
const executable = path.join(
  projectRoot,
  "backend",
  "dist",
  process.platform === "win32" ? "socium-api.exe" : "socium-api",
);
const port = Number(process.env.SOCIUM_BUNDLE_SMOKE_PORT || "8199");
const runtimeRoot = await mkdtemp(path.join(os.tmpdir(), "socium-bundle-smoke-"));
const dataDirectory = path.join(runtimeRoot, "data");

await access(executable);
const child = spawn(executable, ["--host", "127.0.0.1", "--port", String(port)], {
  cwd: projectRoot,
  env: {
    ...process.env,
    SOCIUM_DATA_DIR: dataDirectory,
    SOCIUM_SLACK_SOCKET_MODE: "0",
  },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

async function terminateProcessTree(processToStop) {
  if (processToStop.exitCode !== null) return;
  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const terminator = spawn("taskkill", ["/pid", String(processToStop.pid), "/t", "/f"], {
        stdio: "ignore",
        windowsHide: true,
      });
      terminator.once("error", () => {
        processToStop.kill();
        resolve();
      });
      terminator.once("exit", resolve);
    });
    return;
  }
  processToStop.kill();
}

let stderr = "";
child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => {
  stderr += chunk;
});

try {
  const deadline = Date.now() + 90_000;
  let health;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Bundled API exited with ${child.exitCode}:\n${stderr}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/health`, {
        cache: "no-store",
        signal: AbortSignal.timeout(1_500),
      });
      if (response.ok) {
        health = await response.json();
        break;
      }
    } catch {
      // One-file executables need time to unpack before the first response.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  if (!health) throw new Error(`Bundled API did not become healthy:\n${stderr}`);

  const stateResponse = await fetch(`http://127.0.0.1:${port}/api/state`, {
    cache: "no-store",
    signal: AbortSignal.timeout(5_000),
  });
  if (!stateResponse.ok) throw new Error(`Bundled API state request returned ${stateResponse.status}.`);
  const state = await stateResponse.json();
  const providerResponse = await fetch(`http://127.0.0.1:${port}/api/settings/provider`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      kind: "openai-compatible",
      baseUrl: "https://provider.example/v1",
      model: "bundle-smoke-model",
      apiKey: ["bundle", "smoke", "fixture"].join("-"),
    }),
    signal: AbortSignal.timeout(5_000),
  });
  if (!providerResponse.ok) throw new Error(`Bundled API provider write returned ${providerResponse.status}.`);
  await access(path.join(dataDirectory, "socium.db"));
  await access(path.join(dataDirectory, "master.key"));

  const expectedVersion = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8")).version;
  if (health.version !== expectedVersion || state.features?.edition !== "business-os-v1.4") {
    throw new Error("Bundled API returned the wrong release identity.");
  }
  console.log(
    JSON.stringify(
      {
        ok: true,
        version: health.version,
        database: health.database,
        edition: state.features.edition,
        migrations: "applied",
        encryptedStore: "initialized",
      },
      null,
      2,
    ),
  );
} finally {
  await terminateProcessTree(child);
  await new Promise((resolve) => {
    if (child.exitCode !== null) resolve();
    else child.once("exit", resolve);
  });
  await rm(runtimeRoot, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 });
}
