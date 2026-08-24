import { randomBytes } from "node:crypto";
import { mkdir, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import * as tar from "tar";

import { initializeStorageDirectory, sha256File } from "./installation.mjs";
import { sociumPaths } from "./paths.mjs";
import { loadInstallation } from "./state.mjs";

const BACKUP_PATTERN = /^socium-backup-(.+)\.tar\.gz$/;

async function exists(filePath) {
  try { await stat(filePath); return true; } catch { return false; }
}

function backupName(now = new Date()) {
  return `socium-backup-${now.toISOString().replaceAll(":", "-").replaceAll(".", "-")}.tar.gz`;
}

async function assertStopped(dataDirectory) {
  const lockPath = path.join(dataDirectory, ".socium-runtime.json");
  if (!(await exists(lockPath))) return;
  try {
    const lock = JSON.parse(await readFile(lockPath, "utf8"));
    if (Number.isInteger(lock.pid)) {
      try {
        process.kill(lock.pid, 0);
        throw new Error("Stop Socium before creating or restoring an offline backup.");
      } catch (error) {
        if (!error?.code) throw error;
      }
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export async function createBackup({
  paths = sociumPaths(),
  reason = "manual",
  now = new Date(),
  log = console.log,
  archive = tar.c,
} = {}) {
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed.");
  await assertStopped(installation.dataDirectory);
  await mkdir(paths.backupsDirectory, { recursive: true });
  const filename = backupName(now);
  const destination = path.join(paths.backupsDirectory, filename);
  const partial = `${destination}.partial`;
  const checksumDestination = `${destination}.sha256`;
  const checksumPartial = `${checksumDestination}.partial`;
  const metadata = {
    schemaVersion: 1,
    product: "socium",
    createdAt: now.toISOString(),
    appVersion: installation.version,
    reason,
  };
  const metadataName = `.socium-backup-${process.pid}-${randomBytes(4).toString("hex")}.json`;
  const metadataPath = path.join(installation.dataDirectory, metadataName);
  await writeFile(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`, { flag: "wx" });
  try {
    const entries = await readdir(installation.dataDirectory);
    const selected = entries.filter((entry) => entry !== ".socium-runtime.json" && entry !== "backups" && entry !== metadataName);
    selected.push(metadataName);
    await archive({ cwd: installation.dataDirectory, file: partial, gzip: true, portable: true }, selected);
    const checksum = await sha256File(partial);
    await writeFile(checksumPartial, `${checksum}  ${filename}\n`, { encoding: "utf8", flag: "wx" });
    await rename(partial, destination);
    await rename(checksumPartial, checksumDestination);
    log(`Backup created: ${destination}`);
    return { path: destination, checksum, ...metadata };
  } catch (error) {
    await Promise.all([
      rm(partial, { force: true }),
      rm(checksumPartial, { force: true }),
      rm(destination, { force: true }),
      rm(checksumDestination, { force: true }),
    ]);
    if (error?.code === "ENOSPC") throw new Error("Backup could not be created because the selected drive is full.");
    throw error;
  } finally {
    await rm(metadataPath, { force: true });
  }
}

export async function listBackups({ paths = sociumPaths() } = {}) {
  await mkdir(paths.backupsDirectory, { recursive: true });
  const items = [];
  for (const name of await readdir(paths.backupsDirectory)) {
    if (!BACKUP_PATTERN.test(name)) continue;
    const filePath = path.join(paths.backupsDirectory, name);
    if (!(await exists(`${filePath}.sha256`))) continue;
    const info = await stat(filePath);
    items.push({ name, path: filePath, sizeBytes: info.size, createdAt: info.mtime.toISOString() });
  }
  return items.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export async function restoreBackup({ backupPath, paths = sociumPaths(), log = console.log } = {}) {
  if (!backupPath) throw new Error("Choose a backup with --file PATH.");
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed.");
  await assertStopped(installation.dataDirectory);
  const source = path.resolve(backupPath);
  const expectedPath = `${source}.sha256`;
  if (await exists(expectedPath)) {
    const expected = (await readFile(expectedPath, "utf8")).trim().split(/\s+/)[0];
    if ((await sha256File(source)) !== expected) throw new Error("Backup checksum verification failed.");
  }
  const nonce = `${process.pid}-${randomBytes(4).toString("hex")}`;
  const staging = `${installation.dataDirectory}.restore-${nonce}`;
  const preserved = `${installation.dataDirectory}.before-restore-${Date.now()}`;
  await mkdir(staging, { recursive: true });
  try {
    await tar.x({
      cwd: staging,
      file: source,
      gzip: true,
      strict: true,
      preservePaths: false,
      filter(_name, entry) {
        if (entry.type === "SymbolicLink" || entry.type === "Link") throw new Error("Backup contains a disallowed link entry.");
        return true;
      },
    });
    const marker = JSON.parse(await readFile(path.join(staging, ".socium-storage.json"), "utf8"));
    if (marker.product !== "socium") throw new Error("This is not a Socium data backup.");
    await rename(installation.dataDirectory, preserved);
    try {
      await rename(staging, installation.dataDirectory);
      await initializeStorageDirectory(installation.dataDirectory, { allowExisting: true });
    } catch (error) {
      await rename(preserved, installation.dataDirectory);
      throw error;
    }
    log(`Backup restored. Previous data preserved at ${preserved}`);
    return { dataDirectory: installation.dataDirectory, preservedDirectory: preserved };
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
}
