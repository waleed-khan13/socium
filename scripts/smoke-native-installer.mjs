import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { nativeInstallerFileName } from "./native-installer-names.mjs";

const projectRoot = process.cwd();
const packageJson = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8"));
const targetIndex = process.argv.indexOf("--target");
const target = targetIndex >= 0 ? process.argv[targetIndex + 1] : process.env.SOCIUM_RELEASE_TARGET;
if (!target) throw new Error("--target is required.");

const installerName = nativeInstallerFileName(packageJson.version, target);
const installerPath = path.join(projectRoot, "release", installerName);
const fragment = JSON.parse(await readFile(path.join(projectRoot, "release", `socium-installer-${target}.json`), "utf8"));
if (fragment.file !== installerName || fragment.target !== target || fragment.version !== packageJson.version) {
  throw new Error("Native installer metadata is invalid.");
}
await stat(installerPath);
if (target.startsWith("win32-")) {
  const executableBytes = await readFile(installerPath);
  const peOffset = executableBytes.readUInt32LE(0x3c);
  const subsystem = executableBytes.readUInt16LE(peOffset + 24 + 68);
  if (subsystem !== 2) throw new Error("Windows installer is not a graphical subsystem executable.");
}

// DMG and AppImage containers are built from this exact bootstrap executable; smoke the
// executable directly so CI does not depend on Finder or FUSE.
const executable = target.startsWith("win32-")
  ? installerPath
  : path.join(projectRoot, "native", "installer", "target", "release", "socium-native-installer");
const testHome = await mkdtemp(path.join(os.tmpdir(), "socium-native-installer-"));
try {
  const nativeHome = path.join(testHome, "native-home");
  const child = spawn(
    executable,
    target.startsWith("win32-")
      ? ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", `/DIR=${testHome}`, "/TASKS="]
      : ["--home", testHome, "--install-only", "--no-shortcuts"],
    {
      stdio: "inherit",
      windowsHide: true,
      env: {
        ...process.env,
        APPDATA: path.join(nativeHome, "AppData", "Roaming"),
        OneDrive: path.join(nativeHome, "OneDrive"),
        USERPROFILE: nativeHome,
      },
    },
  );
  const code = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (value) => resolve(value ?? 1));
  });
  if (code !== 0) throw new Error(`Native installer smoke failed with code ${code}.`);
  const installation = JSON.parse(await readFile(path.join(testHome, "installation.json"), "utf8"));
  if (installation.version !== packageJson.version || installation.target !== target) throw new Error("Installer registered the wrong release.");
  await stat(path.join(installation.runtimePath, "web", "server.js"));
  await stat(path.join(installation.runtimePath, "backend", target.startsWith("win32-") ? "socium-api.exe" : "socium-api"));
  if (target.startsWith("win32-")) {
    const bundledIcon = path.join(installation.runtimePath, "native", "socium.ico");
    await stat(bundledIcon);
    await stat(path.join(testHome, "launcher", "node.exe"));
    await stat(path.join(testHome, "launcher", "launch.mjs"));
    const uninstallers = ["unins000.exe", "unins001.exe"];
    if (!(await Promise.all(uninstallers.map((name) => stat(path.join(testHome, name)).then(() => true, () => false)))).some(Boolean)) {
      throw new Error("Graphical Windows installer did not register an uninstaller.");
    }
  }
  console.log(`Native installer smoke passed for ${target}.`);
} finally {
  await rm(testHome, { recursive: true, force: true, maxRetries: 20, retryDelay: 200 });
}
