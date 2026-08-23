import os from "node:os";
import path from "node:path";

export function sociumRoot({
  environment = process.env,
  platform = process.platform,
  homeDirectory = os.homedir(),
} = {}) {
  if (environment.SOCIUM_HOME?.trim()) return assertSafeManagedDirectory(environment.SOCIUM_HOME.trim(), { homeDirectory });

  if (platform === "win32") {
    const localAppData = environment.LOCALAPPDATA?.trim();
    return path.resolve(localAppData || path.join(homeDirectory, "AppData", "Local"), "Socium");
  }
  if (platform === "darwin") {
    return path.resolve(homeDirectory, "Library", "Application Support", "Socium");
  }
  const xdgDataHome = environment.XDG_DATA_HOME?.trim();
  return path.resolve(xdgDataHome || path.join(homeDirectory, ".local", "share"), "socium");
}

export function sociumPaths(options = {}) {
  const root = sociumRoot(options);
  return {
    root,
    backupsDirectory: path.join(root, "backups"),
    launcherDirectory: path.join(root, "launcher"),
    dataDirectory: path.join(root, "data"),
    downloadsDirectory: path.join(root, "downloads"),
    installationFile: path.join(root, "installation.json"),
    modelsDirectory: path.join(root, "models"),
    runtimesDirectory: path.join(root, "runtimes"),
  };
}

export function isPathInside(parent, candidate) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

export function assertSafeManagedDirectory(candidate, { homeDirectory = os.homedir(), label = "Socium directory" } = {}) {
  const resolved = path.resolve(candidate);
  if (resolved === path.parse(resolved).root || resolved === path.resolve(homeDirectory)) {
    throw new Error(`${label} cannot be a drive, filesystem, or home-directory root: ${resolved}`);
  }
  return resolved;
}
