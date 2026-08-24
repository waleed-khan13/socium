import { spawn } from "node:child_process";
import { chmod, copyFile, mkdir, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { sociumPaths } from "./paths.mjs";
import { loadInstallation } from "./state.mjs";

async function exists(filePath) {
  try { await stat(filePath); return true; } catch { return false; }
}

function windowsQuote(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
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

async function writeWindowsLauncher(paths, portable) {
  const scriptPath = path.join(paths.launcherDirectory, "start-socium.ps1");
  const script = `$ErrorActionPreference = 'Stop'\n$env:SOCIUM_HOME = ${windowsQuote(paths.root)}\nStart-Process -FilePath ${windowsQuote(portable.node)} -ArgumentList @(${windowsQuote(portable.script)}) -WorkingDirectory ${windowsQuote(paths.launcherDirectory)} -WindowStyle Hidden\n`;
  await writeFile(scriptPath, script, "utf8");
  return scriptPath;
}

async function createWindowsShortcut(shortcutPath, scriptPath) {
  await mkdir(path.dirname(shortcutPath), { recursive: true });
  const command = `$w=New-Object -ComObject WScript.Shell;$s=$w.CreateShortcut(${windowsQuote(shortcutPath)});$s.TargetPath='powershell.exe';$s.Arguments=${windowsQuote(`-NoProfile -ExecutionPolicy Bypass -File "${scriptPath}"`)};$s.WorkingDirectory=${windowsQuote(path.dirname(scriptPath))};$s.Description='Start Socium';$s.Save()`;
  const child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", command], { windowsHide: true, stdio: "ignore" });
  const code = await new Promise((resolve) => child.once("exit", resolve));
  if (code !== 0) throw new Error("Windows could not create the Socium shortcut.");
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
  const launcher = await writeWindowsLauncher(paths, portable);
  const targets = nativePaths({ platform, environment, homeDirectory });
  if (shortcuts) {
    await createWindowsShortcut(targets.desktop, launcher);
    await createWindowsShortcut(targets.menu, launcher);
  }
  if (autostart) await createWindowsShortcut(targets.autostart, launcher);
  return { launcher, shortcuts, autostart };
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
    const launcher = await writeWindowsLauncher(paths, portable);
    await createWindowsShortcut(targets.autostart, launcher);
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
