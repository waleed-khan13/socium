import { spawn } from "node:child_process";
import { chmod, copyFile, mkdir, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { nativeHelperFileName } from "./platform.mjs";
import { sociumPaths } from "./paths.mjs";
import { loadInstallation } from "./state.mjs";

async function exists(filePath) {
  try { await stat(filePath); return true; } catch { return false; }
}

function xmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function desktopQuote(value) {
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export async function writePortableLauncher(paths, installation, platform = process.platform) {
  await mkdir(paths.launcherDirectory, { recursive: true });
  const bundledNode = path.join(installation.runtimePath, "bin", platform === "win32" ? "node.exe" : "node");
  const stableNode = path.join(paths.launcherDirectory, platform === "win32" ? "node.exe" : "node");
  await copyFile(bundledNode, stableNode);
  if (platform !== "win32") await chmod(stableNode, 0o755);

  const scriptPath = path.join(paths.launcherDirectory, "launch.mjs");
  const script = `import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

const installation = JSON.parse(await readFile(${JSON.stringify(paths.installationFile)}, "utf8"));
const platform = installation.target.split("-")[0];
const node = path.join(installation.runtimePath, "bin", platform === "win32" ? "node.exe" : "node");
const controller = path.join(installation.runtimePath, "controller", "controller.mjs");
const child = spawn(node, [controller, "start", "--tray"], {
  cwd: installation.runtimePath,
  detached: true,
  env: { ...process.env, SOCIUM_HOME: ${JSON.stringify(paths.root)} },
  stdio: "ignore",
  windowsHide: true,
});
child.unref();
`;
  await writeFile(scriptPath, script, "utf8");
  return { node: stableNode, script: scriptPath };
}

export function windowsNativeHelperPath(installation) {
  return path.join(installation.runtimePath, "native", nativeHelperFileName("win32"));
}

export function quoteWindowsArgument(value) {
  return `"${String(value).replaceAll('"', '\\"')}"`;
}

async function runWindowsHelper(helper, arguments_) {
  const child = spawn(helper, arguments_, {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const code = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (value) => resolve(value ?? 1));
  });
  if (code !== 0) throw new Error(stderr.trim() || "The Socium Windows helper failed.");
  return stdout.trim();
}

async function createWindowsShortcut(helper, shortcutPath, portable) {
  await runWindowsHelper(helper, [
    "create-shortcut",
    "--path",
    shortcutPath,
    "--target",
    portable.node,
    "--arguments",
    quoteWindowsArgument(portable.script),
    "--working-directory",
    path.dirname(portable.script),
    "--description",
    "Start Socium",
  ]);
}

export function nativePaths({
  platform = process.platform,
  environment = process.env,
  homeDirectory = os.homedir(),
} = {}) {
  if (platform === "win32") {
    const programs = path.join(environment.APPDATA || path.join(homeDirectory, "AppData", "Roaming"), "Microsoft", "Windows", "Start Menu", "Programs");
    return {
      desktop: path.join(environment.OneDrive || environment.OneDriveCommercial || homeDirectory, "Desktop", "Socium.lnk"),
      menu: path.join(programs, "Socium.lnk"),
      autostart: path.join(programs, "Startup", "Socium.lnk"),
    };
  }
  if (platform === "darwin") return { autostart: path.join(homeDirectory, "Library", "LaunchAgents", "com.socium.app.plist") };
  return { autostart: path.join(environment.XDG_CONFIG_HOME || path.join(homeDirectory, ".config"), "autostart", "socium.desktop") };
}

export async function installNativeIntegration({
  paths = sociumPaths(),
  shortcuts = true,
  autostart = false,
  platform = process.platform,
  environment = process.env,
  homeDirectory = os.homedir(),
} = {}) {
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed.");
  const portable = await writePortableLauncher(paths, installation, platform);
  if (platform !== "win32") {
    const result = await setAutostart({ paths, enabled: autostart, platform, portable, environment, homeDirectory });
    return { ...result, launcher: portable.script, shortcuts: false };
  }
  const helper = windowsNativeHelperPath(installation);
  if (!(await exists(helper))) throw new Error("The installed Windows native helper is missing. Run `socium update --force`.");
  const targets = nativePaths({ platform, environment, homeDirectory });
  if (shortcuts) {
    await createWindowsShortcut(helper, targets.desktop, portable);
    await createWindowsShortcut(helper, targets.menu, portable);
  }
  if (autostart) await createWindowsShortcut(helper, targets.autostart, portable);
  return { launcher: portable.script, shortcuts, autostart };
}

export async function setAutostart({
  paths = sociumPaths(),
  enabled,
  platform = process.platform,
  portable: suppliedPortable,
  environment = process.env,
  homeDirectory = os.homedir(),
} = {}) {
  const targets = nativePaths({ platform, environment, homeDirectory });
  if (!enabled) {
    await rm(targets.autostart, { force: true });
    return { enabled: false, path: targets.autostart };
  }
  const installation = await loadInstallation(paths);
  if (!installation) throw new Error("Socium is not installed.");
  const portable = suppliedPortable || await writePortableLauncher(paths, installation, platform);
  if (platform === "win32") {
    const helper = windowsNativeHelperPath(installation);
    if (!(await exists(helper))) throw new Error("The installed Windows native helper is missing. Run `socium update --force`.");
    await createWindowsShortcut(helper, targets.autostart, portable);
  } else if (platform === "darwin") {
    await mkdir(path.dirname(targets.autostart), { recursive: true });
    await writeFile(targets.autostart, `<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Label</key><string>com.socium.app</string><key>ProgramArguments</key><array><string>${xmlEscape(portable.node)}</string><string>${xmlEscape(portable.script)}</string></array><key>RunAtLoad</key><true/></dict></plist>`, "utf8");
  } else {
    await mkdir(path.dirname(targets.autostart), { recursive: true });
    await writeFile(targets.autostart, `[Desktop Entry]\nType=Application\nName=Socium\nExec=${desktopQuote(portable.node)} ${desktopQuote(portable.script)}\nX-GNOME-Autostart-enabled=true\n`, "utf8");
  }
  return { enabled: true, path: targets.autostart };
}

export async function autostartStatus({ platform = process.platform, environment = process.env, homeDirectory = os.homedir() } = {}) {
  const target = nativePaths({ platform, environment, homeDirectory }).autostart;
  return { enabled: await exists(target), path: target };
}

export async function removeNativeIntegration({ platform = process.platform, environment = process.env, homeDirectory = os.homedir() } = {}) {
  const targets = nativePaths({ platform, environment, homeDirectory });
  for (const target of Object.values(targets)) await rm(target, { force: true });
}
