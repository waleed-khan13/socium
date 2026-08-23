import { randomBytes } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

import { INSTALLATION_SCHEMA_VERSION } from "./constants.mjs";
import { assertSafeManagedDirectory, isPathInside, sociumPaths } from "./paths.mjs";

export async function writeJsonAtomically(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  await rename(temporary, filePath);
}

export async function loadInstallation(paths = sociumPaths()) {
  let state;
  try {
    state = JSON.parse(await readFile(paths.installationFile, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw new Error(`Could not read ${paths.installationFile}: ${error.message}`);
  }
  if (![1, 2, INSTALLATION_SCHEMA_VERSION].includes(state.schemaVersion) || typeof state.runtimePath !== "string") {
    throw new Error("The Socium installation record is invalid. Run `socium update --force`.");
  }
  if (!isPathInside(paths.runtimesDirectory, state.runtimePath)) {
    throw new Error("The Socium installation record points outside the managed runtime directory.");
  }
  if (state.schemaVersion === 1) {
    return {
      ...state,
      schemaVersion: INSTALLATION_SCHEMA_VERSION,
      dataDirectory: paths.dataDirectory,
      modelsDirectory: paths.modelsDirectory,
      legacyInstallation: true,
    };
  }
  if (typeof state.dataDirectory !== "string" || typeof state.modelsDirectory !== "string") {
    throw new Error("The Socium installation record has no durable storage locations. Run `socium update --force`.");
  }
  assertSafeManagedDirectory(state.dataDirectory, { label: "Data directory" });
  assertSafeManagedDirectory(state.modelsDirectory, { label: "Model directory" });
  return { ...state, schemaVersion: INSTALLATION_SCHEMA_VERSION };
}
