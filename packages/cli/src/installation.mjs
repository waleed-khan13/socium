import { createHash, randomBytes } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { chmod, cp, mkdir, readFile, readdir, rename, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pipeline } from "node:stream/promises";
import { Readable, Transform } from "node:stream";

import * as tar from "tar";

import { INSTALLATION_SCHEMA_VERSION, STORAGE_SCHEMA_VERSION } from "./constants.mjs";
import { assertSafeHttpUrl, readJsonSource, resolveAssetSource, validateManifest } from "./manifest.mjs";
import { backendFileName, nativeHelperFileName, releaseTarget } from "./platform.mjs";
import { assertSafeManagedDirectory, isPathInside, sociumPaths } from "./paths.mjs";
import { loadInstallation, writeJsonAtomically } from "./state.mjs";

export { loadInstallation, writeJsonAtomically } from "./state.mjs";

const RELEASE_DOWNLOAD_IDLE_TIMEOUT_MS = 2 * 60_000;

async function pathExists(target) {
  try {
    await stat(target);
    return true;
  } catch {
    return false;
  }
}

async function downloadHttp(source, destination, {
  idleTimeoutMs = RELEASE_DOWNLOAD_IDLE_TIMEOUT_MS,
  onProgress,
} = {}) {
  if (source.startsWith("http://") && process.env.SOCIUM_ALLOW_INSECURE_DOWNLOADS !== "1") {
    throw new Error(`Refusing insecure release asset URL: ${source}`);
  }
  const controller = new AbortController();
  const startedAt = Date.now();
  let downloadedBytes = 0;
  let totalBytes;
  let progressStarted = false;
  let idleTimer;
  const resetIdleTimer = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), idleTimeoutMs);
    idleTimer.unref?.();
  };
  resetIdleTimer();
  try {
    const response = await fetch(source, {
      headers: { "user-agent": "socium-cli" },
      redirect: "follow",
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`Could not download release bundle (${response.status}).`);
    }
    assertSafeHttpUrl(response.url);
    const declaredLength = Number.parseInt(response.headers.get("content-length") || "", 10);
    totalBytes = Number.isSafeInteger(declaredLength) && declaredLength > 0 ? declaredLength : undefined;
    onProgress?.({ downloadedBytes, totalBytes, elapsedMs: Date.now() - startedAt, status: "start" });
    progressStarted = true;
    const progress = new Transform({
      transform(chunk, _encoding, callback) {
        resetIdleTimer();
        downloadedBytes += chunk.byteLength;
        onProgress?.({ downloadedBytes, totalBytes, elapsedMs: Date.now() - startedAt, status: "progress" });
        callback(null, chunk);
      },
    });
    await pipeline(Readable.fromWeb(response.body), progress, createWriteStream(destination, { flags: "wx" }));
    onProgress?.({ downloadedBytes, totalBytes, elapsedMs: Date.now() - startedAt, status: "complete" });
  } catch (error) {
    if (progressStarted) {
      onProgress?.({ downloadedBytes, totalBytes, elapsedMs: Date.now() - startedAt, status: "error" });
    }
    if (controller.signal.aborted) {
      throw new Error(`Release bundle download stalled for more than ${Math.ceil(idleTimeoutMs / 1_000)} seconds.`);
    }
    throw error;
  } finally {
    clearTimeout(idleTimer);
  }
}

async function acquireAsset(source, destination, downloadIdleTimeoutMs, onDownloadProgress) {
  if (source.startsWith("https://") || source.startsWith("http://")) {
    await downloadHttp(source, destination, { idleTimeoutMs: downloadIdleTimeoutMs, onProgress: onDownloadProgress });
    return;
  }
  const sourcePath = source.startsWith("file:") ? fileURLToPath(source) : path.resolve(source);
  await cp(sourcePath, destination, { errorOnExist: true, force: false });
}

export async function sha256File(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

async function directoryIsEmpty(directory) {
  try {
    return (await readdir(directory)).length === 0;
  } catch (error) {
    if (error?.code === "ENOENT") return true;
    throw error;
  }
}

export async function initializeStorageDirectory(dataDirectory, { allowExisting = false } = {}) {
  const resolved = path.resolve(dataDirectory);
  const markerPath = path.join(resolved, ".socium-storage.json");
  if (await pathExists(markerPath)) return markerPath;
  if (!allowExisting && !(await directoryIsEmpty(resolved))) {
    throw new Error(`Data directory is not empty and is not managed by Socium: ${resolved}`);
  }
  await mkdir(resolved, { recursive: true });
  await writeJsonAtomically(markerPath, {
    schemaVersion: STORAGE_SCHEMA_VERSION,
    product: "socium",
    createdAt: new Date().toISOString(),
  });
  return markerPath;
}

export async function initializeModelsDirectory(modelsDirectory, { allowExisting = false } = {}) {
  const resolved = path.resolve(modelsDirectory);
  const markerPath = path.join(resolved, ".socium-models.json");
  if (await pathExists(markerPath)) return markerPath;
  if (!allowExisting && !(await directoryIsEmpty(resolved))) {
    throw new Error(`Model directory is not empty and is not managed by Socium: ${resolved}`);
  }
  await mkdir(resolved, { recursive: true });
  await writeJsonAtomically(markerPath, {
    schemaVersion: STORAGE_SCHEMA_VERSION,
    product: "socium-models",
    createdAt: new Date().toISOString(),
  });
  return markerPath;
}

function versionParts(value) {
  const match = String(value).match(/^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
  if (!match) throw new Error(`Invalid release version: ${value}`);
  return match.slice(1).map(Number);
}

function compareReleaseVersions(left, right) {
  const a = versionParts(left);
  const b = versionParts(right);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  }
  return 0;
}

export async function registerBundledRuntime({
  runtimePath,
  version,
  target,
  manifestSource,
  paths = sociumPaths(),
  dataDirectory,
  modelsDirectory,
} = {}) {
  if (!runtimePath || !version || !target || !manifestSource) {
    throw new Error("Runtime path, version, target, and manifest source are required.");
  }
  const resolvedRuntimePath = path.resolve(runtimePath);
  if (!isPathInside(paths.runtimesDirectory, resolvedRuntimePath)) {
    throw new Error("Bundled runtime resolves outside the managed runtime directory.");
  }
  await validateBundle(resolvedRuntimePath, version, target);

  const previous = await loadInstallation(paths);
  if (previous && compareReleaseVersions(previous.version, version) > 0) return previous;
  if (previous && dataDirectory && path.resolve(dataDirectory) !== path.resolve(previous.dataDirectory)) {
    throw new Error("Socium is already installed. Change the existing data location safely from the dashboard.");
  }
  if (previous && modelsDirectory && path.resolve(modelsDirectory) !== path.resolve(previous.modelsDirectory)) {
    throw new Error("Socium is already installed. Change the existing model location safely from the dashboard.");
  }

  const selectedDataDirectory = assertSafeManagedDirectory(
    dataDirectory || previous?.dataDirectory || paths.dataDirectory,
    { label: "Data directory" },
  );
  const selectedModelsDirectory = assertSafeManagedDirectory(
    modelsDirectory || previous?.modelsDirectory || paths.modelsDirectory,
    { label: "Model directory" },
  );
  if (
    selectedDataDirectory === selectedModelsDirectory ||
    isPathInside(selectedDataDirectory, selectedModelsDirectory) ||
    isPathInside(selectedModelsDirectory, selectedDataDirectory)
  ) {
    throw new Error("Data and local AI models must use separate directories.");
  }
  for (const selected of [selectedDataDirectory, selectedModelsDirectory]) {
    if (
      selected === paths.root ||
      isPathInside(paths.runtimesDirectory, selected) ||
      isPathInside(paths.downloadsDirectory, selected) ||
      isPathInside(selected, paths.runtimesDirectory) ||
      isPathInside(selected, paths.downloadsDirectory)
    ) {
      throw new Error("Durable data and models cannot be stored inside Socium's replaceable runtime directories.");
    }
  }

  await initializeStorageDirectory(selectedDataDirectory, { allowExisting: Boolean(previous?.legacyInstallation) });
  await initializeModelsDirectory(selectedModelsDirectory, { allowExisting: Boolean(previous?.legacyInstallation) });
  await mkdir(path.join(selectedDataDirectory, "logs"), { recursive: true });

  const sameRuntime = previous?.runtimePath === resolvedRuntimePath;
  const installation = {
    schemaVersion: INSTALLATION_SCHEMA_VERSION,
    version,
    target,
    runtimePath: resolvedRuntimePath,
    dataDirectory: selectedDataDirectory,
    modelsDirectory: selectedModelsDirectory,
    installedAt: new Date().toISOString(),
    manifestSource,
    previousRelease: sameRuntime
      ? previous?.previousRelease || null
      : previous
        ? {
            version: previous.version,
            target: previous.target,
            runtimePath: previous.runtimePath,
            backupPath: null,
          }
        : null,
  };
  await writeJsonAtomically(paths.installationFile, installation);
  return installation;
}

async function validateBundle(runtimePath, version, target) {
  const metadataPath = path.join(runtimePath, "bundle.json");
  const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
  if (
    ![1, 2, 3].includes(metadata.schemaVersion) ||
    metadata.product !== "socium" ||
    metadata.version !== version ||
    metadata.target !== target
  ) {
    throw new Error("Downloaded bundle metadata does not match the selected release.");
  }
  const required = [
    path.join(runtimePath, "web", "server.js"),
    path.join(runtimePath, "backend", backendFileName(target.split("-")[0])),
  ];
  if (metadata.schemaVersion >= 2) {
    required.push(
      path.join(runtimePath, "bin", target.startsWith("win32-") ? "node.exe" : "node"),
      path.join(runtimePath, "controller", "controller.mjs"),
      path.join(runtimePath, "controller", "managed-cli.mjs"),
    );
  }
  if (metadata.schemaVersion >= 3 && target.startsWith("win32-")) {
    required.push(path.join(runtimePath, "native", nativeHelperFileName("win32")));
  }
  for (const filePath of required) {
    if (!(await pathExists(filePath))) throw new Error(`Downloaded bundle is missing ${path.relative(runtimePath, filePath)}.`);
  }
  if (!target.startsWith("win32-")) {
    await chmod(required[1], 0o755);
    if (metadata.schemaVersion >= 2) await chmod(required[2], 0o755);
  }
}

export async function installRelease({
  manifestSource,
  paths = sociumPaths(),
  target = releaseTarget(),
  force = false,
  downloadIdleTimeoutMs = RELEASE_DOWNLOAD_IDLE_TIMEOUT_MS,
  onDownloadProgress,
  dataDirectory,
  modelsDirectory,
  backupPath,
  log = console.log,
} = {}) {
  if (!manifestSource) throw new Error("A release manifest source is required.");
  const previous = await loadInstallation(paths);
  if (previous && dataDirectory && path.resolve(dataDirectory) !== path.resolve(previous.dataDirectory)) {
    throw new Error("Socium is already installed. Use `socium storage move --data-dir <path>` to move existing data safely.");
  }
  if (previous && modelsDirectory && path.resolve(modelsDirectory) !== path.resolve(previous.modelsDirectory)) {
    throw new Error("Socium is already installed. Use `socium storage move --models-dir <path>` to move existing models safely.");
  }
  const selectedDataDirectory = assertSafeManagedDirectory(dataDirectory || previous?.dataDirectory || paths.dataDirectory, { label: "Data directory" });
  const selectedModelsDirectory = assertSafeManagedDirectory(modelsDirectory || previous?.modelsDirectory || paths.modelsDirectory, { label: "Model directory" });
  if (selectedDataDirectory === selectedModelsDirectory || isPathInside(selectedDataDirectory, selectedModelsDirectory) || isPathInside(selectedModelsDirectory, selectedDataDirectory)) {
    throw new Error("Data and local AI models must use separate directories.");
  }
  for (const selected of [selectedDataDirectory, selectedModelsDirectory]) {
    if (selected === paths.root || isPathInside(paths.runtimesDirectory, selected) || isPathInside(paths.downloadsDirectory, selected) || isPathInside(selected, paths.runtimesDirectory) || isPathInside(selected, paths.downloadsDirectory)) {
      throw new Error("Durable data and models cannot be stored inside Socium's replaceable runtime directories.");
    }
  }
  await mkdir(paths.downloadsDirectory, { recursive: true });
  await mkdir(paths.runtimesDirectory, { recursive: true });
  await initializeStorageDirectory(selectedDataDirectory, { allowExisting: Boolean(previous?.legacyInstallation) });
  await initializeModelsDirectory(selectedModelsDirectory, { allowExisting: Boolean(previous?.legacyInstallation) });
  await mkdir(path.join(selectedDataDirectory, "logs"), { recursive: true });

  const manifest = await readJsonSource(manifestSource);
  const { asset, version } = validateManifest(manifest, target);
  const assetSource = resolveAssetSource(asset.url, manifestSource);
  const nonce = `${process.pid}-${randomBytes(5).toString("hex")}`;
  const archivePath = path.join(paths.downloadsDirectory, `${target}-${nonce}.tar.gz`);
  const runtimePath = path.join(paths.runtimesDirectory, version, target);
  const stagingPath = `${runtimePath}.staging-${nonce}`;
  if (!isPathInside(paths.runtimesDirectory, runtimePath)) {
    throw new Error("Release version resolves outside the managed runtime directory.");
  }

  log(`Downloading Socium ${version} for ${target}...`);
  try {
    await acquireAsset(assetSource, archivePath, downloadIdleTimeoutMs, onDownloadProgress);
    const actualChecksum = await sha256File(archivePath);
    if (actualChecksum.toLowerCase() !== asset.sha256.toLowerCase()) {
      throw new Error("Release bundle checksum verification failed. The archive was not installed.");
    }

    await mkdir(stagingPath, { recursive: true });
    await tar.x({
      cwd: stagingPath,
      file: archivePath,
      gzip: true,
      strict: true,
      preservePaths: false,
      filter(_entryPath, entry) {
        if (entry.type === "SymbolicLink" || entry.type === "Link") {
          throw new Error("Release bundle contains a disallowed link entry.");
        }
        return true;
      },
    });
    await validateBundle(stagingPath, version, target);

    let replacedRuntimePath = null;
    if (await pathExists(runtimePath)) {
      if (!force) {
        await rm(stagingPath, { recursive: true, force: true, maxRetries: 20, retryDelay: 200 });
      } else {
        replacedRuntimePath = `${runtimePath}.previous-${nonce}`;
        await rename(runtimePath, replacedRuntimePath);
        await mkdir(path.dirname(runtimePath), { recursive: true });
        try {
          await rename(stagingPath, runtimePath);
        } catch (error) {
          await rename(replacedRuntimePath, runtimePath);
          throw error;
        }
      }
    } else {
      await mkdir(path.dirname(runtimePath), { recursive: true });
      await rename(stagingPath, runtimePath);
    }

    const installation = {
      schemaVersion: INSTALLATION_SCHEMA_VERSION,
      version,
      target,
      runtimePath,
      dataDirectory: selectedDataDirectory,
      modelsDirectory: selectedModelsDirectory,
      installedAt: new Date().toISOString(),
      manifestSource,
      previousRelease: previous
        ? {
            version: previous.version,
            target: previous.target,
            runtimePath: replacedRuntimePath || previous.runtimePath,
            backupPath: backupPath || null,
          }
        : null,
    };
    await writeJsonAtomically(paths.installationFile, installation);
    log(`Installed Socium ${version} at ${runtimePath}`);
    return installation;
  } finally {
    await rm(archivePath, { force: true, maxRetries: 20, retryDelay: 200 });
    await rm(stagingPath, { recursive: true, force: true, maxRetries: 20, retryDelay: 200 });
  }
}
