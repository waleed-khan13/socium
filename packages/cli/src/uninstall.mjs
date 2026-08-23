import { access, rm } from "node:fs/promises";
import path from "node:path";

import { isPathInside, sociumPaths } from "./paths.mjs";
import { loadInstallation } from "./installation.mjs";

export async function uninstall({ paths = sociumPaths(), purgeData = false, confirmed = false } = {}) {
  if (!confirmed) {
    throw new Error("Uninstall requires --yes. Local business data is preserved unless --purge-data is also supplied.");
  }
  const installation = await loadInstallation(paths);
  if (purgeData) {
    if (installation && !installation.legacyInstallation) {
      await access(path.join(installation.dataDirectory, ".socium-storage.json"));
      await access(path.join(installation.modelsDirectory, ".socium-models.json"));
    }
    const externalTargets = [installation?.dataDirectory, installation?.modelsDirectory]
      .filter(Boolean)
      .filter((target) => target !== paths.root && !isPathInside(paths.root, target));
    await Promise.all(externalTargets.map((target) => rm(target, { force: true, recursive: true, maxRetries: 20, retryDelay: 200 })));
    await rm(paths.root, { force: true, recursive: true, maxRetries: 20, retryDelay: 200 });
    return { purgedData: true, preservedData: false };
  }

  await Promise.all([
    rm(paths.runtimesDirectory, { force: true, recursive: true, maxRetries: 20, retryDelay: 200 }),
    rm(paths.downloadsDirectory, { force: true, recursive: true, maxRetries: 20, retryDelay: 200 }),
    rm(paths.launcherDirectory, { force: true, recursive: true, maxRetries: 20, retryDelay: 200 }),
    rm(paths.installationFile, { force: true }),
  ]);
  return { purgedData: false, preservedData: true, dataDirectory: installation?.dataDirectory || paths.dataDirectory };
}
