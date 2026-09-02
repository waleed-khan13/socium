import { spawn } from "node:child_process";
import path from "node:path";

import { findAvailablePort } from "../packages/cli/src/ports.mjs";

const projectRoot = process.cwd();
const preferredApiPort = Number(process.env.SOCIUM_API_PORT || "8000");
const preferredWebPort = Number(process.env.PORT || "3000");
const apiPort = await findAvailablePort(preferredApiPort);
const webPort = await findAvailablePort(preferredWebPort, { exclude: [apiPort] });
const dataDirectory = process.env.SOCIUM_DATA_DIR || path.join(projectRoot, "data");
const children = new Set();
let stopping = false;

if (apiPort !== preferredApiPort) {
  console.log(`Internal API port ${preferredApiPort} is busy; Socium selected ${apiPort}.`);
}
if (webPort !== preferredWebPort) {
  console.log(`Web port ${preferredWebPort} is busy; Socium selected ${webPort}.`);
}
console.log(`Socium will be available at http://127.0.0.1:${webPort}`);

function launch(command, args, extraEnv = {}) {
  const child = spawn(command, args, {
    cwd: projectRoot,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
    windowsHide: true,
  });
  children.add(child);
  child.on("exit", (code) => {
    children.delete(child);
    if (!stopping) shutdown(code ?? 1);
  });
  return child;
}

function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill();
  setTimeout(() => process.exit(code), 50).unref();
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => shutdown(0));
}

launch(
  "uv",
  [
    "run",
    "--project",
    "backend",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(apiPort),
  ],
  {
    SOCIUM_API_HOST: "127.0.0.1",
    SOCIUM_API_PORT: String(apiPort),
    SOCIUM_DATA_DIR: dataDirectory,
  },
);
launch(
  process.execPath,
  [
    path.join(projectRoot, "node_modules", "next", "dist", "bin", "next"),
    "dev",
    "-H",
    "127.0.0.1",
    "-p",
    String(webPort),
    "--webpack",
  ],
  {
    SOCIUM_API_URL: `http://127.0.0.1:${apiPort}`,
  },
);
