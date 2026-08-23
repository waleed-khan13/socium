import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DEFAULT_API_PORT, DEFAULT_WEB_PORT } from "./constants.mjs";
import { loadInstallation } from "./state.mjs";
import { backendFileName } from "./platform.mjs";
import { sociumPaths } from "./paths.mjs";

async function exists(filePath) {
  try {
    await stat(filePath);
    return true;
  } catch {
    return false;
  }
}

export function runtimeLayout(installation) {
  const platform = installation.target.split("-")[0];
  return {
    apiExecutable: path.join(installation.runtimePath, "backend", backendFileName(platform)),
    webDirectory: path.join(installation.runtimePath, "web"),
    webServer: path.join(installation.runtimePath, "web", "server.js"),
    nodeExecutable: path.join(installation.runtimePath, "bin", platform === "win32" ? "node.exe" : "node"),
  };
}

export async function isPortAvailable(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host, port }, () => server.close(() => resolve(true)));
  });
}

async function waitForHttp(url, child, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    if (child?.exitCode !== null) throw new Error(`Socium process exited before ${url} became ready.`);
    try {
      const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(1_500) });
      if (response.ok) return response;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message ?? "unknown error"}`);
}

export function openBrowser(url, platform = process.platform) {
  const command =
    platform === "win32"
      ? ["cmd", ["/c", "start", "", url]]
      : platform === "darwin"
        ? ["open", [url]]
        : ["xdg-open", [url]];
  const child = spawn(command[0], command[1], { detached: true, stdio: "ignore", windowsHide: true });
  child.once("error", () => {});
  child.unref();
}

function terminateProcessTree(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === "win32") {
    const terminator = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "ignore",
      windowsHide: true,
    });
    terminator.once("error", () => child.kill());
    return;
  }
  child.kill();
}

function launchUpdateHelper({ manifestSource, restart, waitPid, rollback = false }) {
  const executable = process.execPath;
  const managedCli = path.join(path.dirname(fileURLToPath(import.meta.url)), "managed-cli.mjs");
  const args = [managedCli, rollback ? "rollback" : "update", "--from-app", "--wait-pid", String(waitPid)];
  if (manifestSource) args.push("--manifest", manifestSource);
  if (restart) args.push("--restart");
  const child = spawn(executable, args, { detached: true, stdio: "ignore", windowsHide: true });
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("spawn", () => {
      child.unref();
      resolve(child.pid);
    });
  });
}

async function createControlServer({ token, state, onAction }) {
  const server = createServer(async (request, response) => {
    response.setHeader("content-type", "application/json");
    if (request.headers.authorization !== `Bearer ${token}`) {
      response.writeHead(401).end(JSON.stringify({ ok: false, error: "Unauthorized" }));
      return;
    }
    if (request.method === "GET" && request.url === "/status") {
      response.end(JSON.stringify({ ok: true, ...state() }));
      return;
    }
    if (request.method === "POST" && ["/stop", "/restart", "/update", "/rollback"].includes(request.url)) {
      const action = request.url.slice(1);
      response.end(JSON.stringify({ ok: true, action }));
      setTimeout(() => Promise.resolve(onAction(action)).catch(() => undefined), 150).unref?.();
      return;
    }
    response.writeHead(404).end(JSON.stringify({ ok: false, error: "Not found" }));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port: 0 }, resolve);
  });
  server.unref();
  return server;
}

async function alreadyRunning(webPort) {
  try {
    const response = await fetch(`http://127.0.0.1:${webPort}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1_500),
    });
    const body = await response.json();
    return response.ok && body?.service === "socium-api";
  } catch {
    return false;
  }
}

export async function startRuntime({
  paths = sociumPaths(),
  webPort = DEFAULT_WEB_PORT,
  apiPort = DEFAULT_API_PORT,
  shouldOpenBrowser = true,
  labsEnabled = false,
  updateManifest,
  log = console.log,
} = {}) {
  if (!(await isPortAvailable(webPort))) {
    if (await alreadyRunning(webPort)) {
      const url = `http://127.0.0.1:${webPort}`;
      log(`Socium is already running at ${url}`);
      if (shouldOpenBrowser) openBrowser(url);
      return { alreadyRunning: true, url };
    }
    throw new Error(`Port ${webPort} is already in use. Choose another port with --port.`);
  }
  if (!(await isPortAvailable(apiPort))) {
    throw new Error(`Internal API port ${apiPort} is already in use. Choose another port with --api-port.`);
  }

  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed. Run `socium onboard` first.");
  const layout = runtimeLayout(installation);
  if (!(await exists(layout.apiExecutable)) || !(await exists(layout.webServer))) {
    throw new Error("The installed runtime is incomplete. Run `socium update --force`.");
  }
  const storageMarker = path.join(installation.dataDirectory, ".socium-storage.json");
  if (!(await exists(installation.dataDirectory)) || (!(await exists(storageMarker)) && !installation.legacyInstallation)) {
    throw new Error(`Data drive unavailable: ${installation.dataDirectory}`);
  }
  if (installation.legacyInstallation && !(await exists(storageMarker))) {
    await mkdir(installation.dataDirectory, { recursive: true });
    await writeFile(storageMarker, `${JSON.stringify({ schemaVersion: 1, product: "socium", createdAt: new Date().toISOString() }, null, 2)}\n`, { flag: "wx" });
  }
  const modelsMarker = path.join(installation.modelsDirectory, ".socium-models.json");
  if (!(await exists(installation.modelsDirectory)) || (!(await exists(modelsMarker)) && !installation.legacyInstallation)) {
    throw new Error(`Local AI model drive unavailable: ${installation.modelsDirectory}`);
  }
  if (installation.legacyInstallation && !(await exists(modelsMarker))) {
    await mkdir(installation.modelsDirectory, { recursive: true });
    await writeFile(modelsMarker, `${JSON.stringify({ schemaVersion: 1, product: "socium-models", createdAt: new Date().toISOString() }, null, 2)}\n`, { flag: "wx" });
  }

  const runtimeLock = path.join(installation.dataDirectory, ".socium-runtime.json");
  try {
    const existingLock = JSON.parse(await readFile(runtimeLock, "utf8"));
    if (Number.isInteger(existingLock.pid)) {
      try {
        process.kill(existingLock.pid, 0);
        throw new Error(`Socium is already using this data directory (process ${existingLock.pid}).`);
      } catch (error) {
        if (!error?.code) throw error;
      }
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const children = new Set();
  let stopping = false;
  let requestedAction = "stop";
  const launch = (command, args, options) => {
    const child = spawn(command, args, { stdio: "inherit", windowsHide: true, ...options });
    children.add(child);
    child.once("exit", () => children.delete(child));
    return child;
  };
  const stop = (action = "stop") => {
    if (stopping) return;
    requestedAction = action;
    stopping = true;
    for (const child of children) terminateProcessTree(child);
  };

  const controlToken = randomBytes(24).toString("hex");
  const controlServer = await createControlServer({
    token: controlToken,
    state: () => ({ version: installation.version, webPort, apiPort, pid: process.pid }),
    async onAction(action) {
      if (action === "update") {
        const preparedManifest = path.join(installation.dataDirectory, ".updates", "prepared-manifest.json");
        await launchUpdateHelper({ manifestSource: await exists(preparedManifest) ? preparedManifest : updateManifest || installation.manifestSource, restart: true, waitPid: process.pid });
      }
      if (action === "rollback") await launchUpdateHelper({ restart: true, waitPid: process.pid, rollback: true });
      stop(action);
    },
  });
  const controlPort = controlServer.address().port;
  await writeFile(runtimeLock, `${JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString(), webPort, apiPort, controlPort, controlToken, version: installation.version })}\n`, { flag: "w" });

  const signalHandlers = new Map();
  for (const signal of ["SIGINT", "SIGTERM"]) {
    const handler = () => stop();
    signalHandlers.set(signal, handler);
    process.once(signal, handler);
  }

  const sharedEnvironment = {
    ...process.env,
    SOCIUM_API_HOST: "127.0.0.1",
    SOCIUM_API_PORT: String(apiPort),
    SOCIUM_DATA_DIR: installation.dataDirectory,
    SOCIUM_MODELS_DIR: installation.modelsDirectory,
    SOCIUM_RUNTIME_DIR: installation.runtimePath,
    SOCIUM_STORAGE_REQUIRE_MARKER: "1",
    SOCIUM_ENABLE_LABS: labsEnabled ? "1" : "0",
    SOCIUM_CONTROL_URL: `http://127.0.0.1:${controlPort}`,
    SOCIUM_CONTROL_TOKEN: controlToken,
    SOCIUM_APP_VERSION: installation.version,
    SOCIUM_RELEASE_TARGET: installation.target,
    SOCIUM_RELEASE_MANIFEST: updateManifest || installation.manifestSource || "",
  };

  try {
    const api = launch(layout.apiExecutable, ["--host", "127.0.0.1", "--port", String(apiPort)], {
      cwd: installation.runtimePath,
      env: sharedEnvironment,
    });
    await waitForHttp(`http://127.0.0.1:${apiPort}/api/health`, api);

    const nodeExecutable = (await exists(layout.nodeExecutable)) ? layout.nodeExecutable : process.execPath;
    const web = launch(nodeExecutable, [layout.webServer], {
      cwd: layout.webDirectory,
      env: {
        ...sharedEnvironment,
        HOSTNAME: "127.0.0.1",
        PORT: String(webPort),
        SOCIUM_API_URL: `http://127.0.0.1:${apiPort}`,
        NODE_ENV: "production",
      },
    });
    const url = `http://127.0.0.1:${webPort}`;
    await waitForHttp(`${url}/api/health`, web);
    log(`Socium ${installation.version} is running at ${url}`);
    if (shouldOpenBrowser) openBrowser(url);

    const exitCode = await new Promise((resolve) => {
      api.once("exit", (code) => resolve(code ?? 1));
      web.once("exit", (code) => resolve(code ?? 0));
    });
    stop();
    return { alreadyRunning: false, exitCode, url, action: requestedAction };
  } finally {
    stop();
    await new Promise((resolve) => controlServer.close(resolve));
    await rm(runtimeLock, { force: true });
    for (const [signal, handler] of signalHandlers) process.removeListener(signal, handler);
  }
}
