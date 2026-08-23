import { createHash, randomBytes } from "node:crypto";
import { createReadStream } from "node:fs";
import { cp, mkdir, readFile, readdir, rename, rm, stat } from "node:fs/promises";
import path from "node:path";

import { loadInstallation, writeJsonAtomically } from "./installation.mjs";
import { assertSafeManagedDirectory, isPathInside, sociumPaths } from "./paths.mjs";

async function exists(target) {
  try {
    await stat(target);
    return true;
  } catch {
    return false;
  }
}

async function processIsRunning(pid) {
  if (!Number.isInteger(pid) || pid < 1) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

async function assertRuntimeStopped(dataDirectory) {
  const lockPath = path.join(dataDirectory, ".socium-runtime.json");
  try {
    const lock = JSON.parse(await readFile(lockPath, "utf8"));
    if (await processIsRunning(lock.pid)) {
      throw new Error("Socium is running. Stop it before moving durable storage so SQLite can close safely.");
    }
  } catch (error) {
    if (error?.code !== "ENOENT" && !String(error?.message).includes("Unexpected")) throw error;
  }
}

async function fileDigest(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

async function directoryManifest(root) {
  if (!(await exists(root))) return [];
  const entries = [];
  async function visit(current) {
    const children = await readdir(current, { withFileTypes: true });
    for (const child of children) {
      if (child.name === ".socium-runtime.json") continue;
      const absolute = path.join(current, child.name);
      if (child.isDirectory()) await visit(absolute);
      else if (child.isFile()) {
        const metadata = await stat(absolute);
        entries.push({
          path: path.relative(root, absolute).split(path.sep).join("/"),
          size: metadata.size,
          sha256: await fileDigest(absolute),
        });
      }
    }
  }
  await visit(root);
  return entries.sort((left, right) => left.path.localeCompare(right.path));
}

async function stageDirectory(source, destination) {
  if (path.resolve(source) === path.resolve(destination)) return null;
  if (await exists(destination)) throw new Error(`Destination already exists. Choose a new empty path: ${destination}`);
  const staging = `${destination}.socium-staging-${process.pid}-${randomBytes(4).toString("hex")}`;
  await mkdir(path.dirname(destination), { recursive: true });
  await cp(source, staging, { recursive: true, force: false, filter: (item) => path.basename(item) !== ".socium-runtime.json" });
  const [sourceManifest, stagedManifest] = await Promise.all([
    directoryManifest(source),
    directoryManifest(staging),
  ]);
  if (JSON.stringify(sourceManifest) !== JSON.stringify(stagedManifest)) {
    await rm(staging, { recursive: true, force: true });
    throw new Error(`Verification failed while copying ${source}. The active location was not changed.`);
  }
  return { destination, staging };
}

export async function relocateStorage({ paths = sociumPaths(), dataDirectory, modelsDirectory } = {}) {
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed. Run `socium onboard` first.");
  await assertRuntimeStopped(installation.dataDirectory);

  const nextData = assertSafeManagedDirectory(dataDirectory || installation.dataDirectory, { label: "Data directory" });
  const nextModels = assertSafeManagedDirectory(modelsDirectory || installation.modelsDirectory, { label: "Model directory" });
  if (nextData === nextModels || isPathInside(nextData, nextModels) || isPathInside(nextModels, nextData)) {
    throw new Error("Data and local AI models must use separate directories.");
  }
  for (const selected of [nextData, nextModels]) {
    if (selected === paths.root || isPathInside(paths.runtimesDirectory, selected) || isPathInside(paths.downloadsDirectory, selected) || isPathInside(selected, paths.runtimesDirectory) || isPathInside(selected, paths.downloadsDirectory)) {
      throw new Error("Durable data and models cannot be moved inside Socium's replaceable runtime directories.");
    }
  }

  const staged = [];
  try {
    const dataStage = await stageDirectory(installation.dataDirectory, nextData);
    if (dataStage) staged.push(dataStage);
    const modelStage = await stageDirectory(installation.modelsDirectory, nextModels);
    if (modelStage) staged.push(modelStage);
    for (const item of staged) await rename(item.staging, item.destination);
    const updated = {
      ...installation,
      schemaVersion: 2,
      dataDirectory: nextData,
      modelsDirectory: nextModels,
      storageMovedAt: new Date().toISOString(),
    };
    delete updated.legacyInstallation;
    await writeJsonAtomically(paths.installationFile, updated);
    return {
      installation: updated,
      previousDataDirectory: installation.dataDirectory,
      previousModelsDirectory: installation.modelsDirectory,
      sourcePreserved: true,
    };
  } catch (error) {
    for (const item of staged) await rm(item.staging, { recursive: true, force: true });
    throw error;
  }
}
