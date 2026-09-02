import { access, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import path from "node:path";

import { DEFAULT_API_PORT, DEFAULT_WEB_PORT } from "./constants.mjs";
import { loadInstallation } from "./installation.mjs";
import { sociumPaths } from "./paths.mjs";
import { isPortAvailable, runtimeLayout } from "./runtime.mjs";

function nodeVersionOkay(version = process.versions.node) {
  const [major, minor] = version.split(".").map(Number);
  return major > 20 || (major === 20 && minor >= 9);
}

export async function diagnose({
  paths = sociumPaths(),
  webPort = DEFAULT_WEB_PORT,
  apiPort = DEFAULT_API_PORT,
} = {}) {
  const checks = [];
  checks.push({ name: "Node.js 20.9+", ok: nodeVersionOkay(), detail: process.versions.node });

  let installation;
  try {
    installation = await loadInstallation(paths);
    checks.push({
      name: "Installation record",
      ok: Boolean(installation),
      detail: installation ? `${installation.version} (${installation.target})` : "not installed",
    });
  } catch (error) {
    checks.push({ name: "Installation record", ok: false, detail: error.message });
  }

  if (installation) {
    const layout = runtimeLayout(installation);
    let bundleSchemaVersion = 1;
    try {
      const bundle = JSON.parse(await readFile(path.join(installation.runtimePath, "bundle.json"), "utf8"));
      if (Number.isInteger(bundle.schemaVersion)) bundleSchemaVersion = bundle.schemaVersion;
    } catch {
      // The core runtime checks below still report a damaged or incomplete installation.
    }
    for (const [name, filePath] of [
      ["FastAPI runtime", layout.apiExecutable],
      ["Next.js runtime", layout.webServer],
      ...(layout.nativeHelper && bundleSchemaVersion >= 3 ? [["Windows native helper", layout.nativeHelper]] : []),
    ]) {
      try {
        await access(filePath);
        checks.push({ name, ok: true, detail: filePath });
      } catch {
        checks.push({ name, ok: false, detail: `missing: ${filePath}` });
      }
    }
  }

  const dataDirectory = installation?.dataDirectory || paths.dataDirectory;
  const modelsDirectory = installation?.modelsDirectory || paths.modelsDirectory;
  try {
    if (installation && !installation.legacyInstallation) await access(path.join(dataDirectory, ".socium-storage.json"));
    else await mkdir(dataDirectory, { recursive: true });
    const probe = path.join(dataDirectory, `.doctor-${process.pid}`);
    await writeFile(probe, "ok", { flag: "wx" });
    await rm(probe, { force: true });
    checks.push({ name: "Data directory", ok: true, detail: dataDirectory });
  } catch (error) {
    checks.push({ name: "Data directory", ok: false, detail: error.message });
  }

  try {
    if (installation && !installation.legacyInstallation) await access(path.join(modelsDirectory, ".socium-models.json"));
    else await mkdir(modelsDirectory, { recursive: true });
    const probe = path.join(modelsDirectory, `.doctor-${process.pid}`);
    await writeFile(probe, "ok", { flag: "wx" });
    await rm(probe, { force: true });
    checks.push({ name: "Model directory", ok: true, detail: modelsDirectory });
  } catch (error) {
    checks.push({ name: "Model directory", ok: false, detail: error.message });
  }

  const webPortAvailable = await isPortAvailable(webPort);
  checks.push({
    name: `Web port ${webPort}`,
    ok: webPortAvailable,
    detail: webPortAvailable ? "available" : "occupied (Socium may already be running)",
    advisory: true,
  });
  const apiPortAvailable = await isPortAvailable(apiPort);
  checks.push({
    name: `API port ${apiPort}`,
    ok: apiPortAvailable,
    detail: apiPortAvailable ? "available" : "occupied (Socium may already be running)",
    advisory: true,
  });

  return {
    ok: checks.every((check) => check.ok || check.advisory),
    root: paths.root,
    checks,
  };
}
