import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, chmod, cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

import { nativeInstallerFileName } from "./native-installer-names.mjs";

const projectRoot = process.cwd();
const packageJson = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8"));
const version = packageJson.version;
const targetIndex = process.argv.indexOf("--target");
const target = targetIndex >= 0 ? process.argv[targetIndex + 1] : process.env.SOCIUM_RELEASE_TARGET;
if (!target) throw new Error("--target is required.");

const releaseDirectory = path.join(projectRoot, "release");
const archive = path.join(releaseDirectory, `socium-${version}-${target}.tar.gz`);
const fragmentPath = path.join(releaseDirectory, `socium-asset-${target}.json`);
await access(archive);
const fragment = JSON.parse(await readFile(fragmentPath, "utf8"));
if (fragment.version !== version || fragment.target !== target) throw new Error("Runtime fragment does not match this installer build.");

async function run(command, arguments_, options = {}) {
  const child = spawn(command, arguments_, { cwd: projectRoot, stdio: "inherit", windowsHide: true, ...options });
  const code = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (value) => resolve(value ?? 1));
  });
  if (code !== 0) throw new Error(`${command} exited with code ${code}.`);
}

async function sha256(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

async function windowsBuildEnvironment() {
  if (process.platform !== "win32") return process.env;
  const programFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  const vswhere = path.join(programFilesX86, "Microsoft Visual Studio", "Installer", "vswhere.exe");
  try { await access(vswhere); } catch { return process.env; }
  const query = spawn(vswhere, ["-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], { stdio: ["ignore", "pipe", "ignore"], windowsHide: true });
  let installationPath = "";
  query.stdout.setEncoding("utf8");
  query.stdout.on("data", (chunk) => { installationPath += chunk; });
  const queryCode = await new Promise((resolve) => query.once("exit", (code) => resolve(code ?? 1)));
  if (queryCode !== 0 || !installationPath.trim()) return process.env;
  const vcvars = path.join(installationPath.trim(), "VC", "Auxiliary", "Build", process.arch === "arm64" ? "vcvarsarm64.bat" : "vcvars64.bat");
  const environmentProcess = spawn("cmd.exe", ["/d", "/c", `call "${vcvars}" >nul && set`], { stdio: ["ignore", "pipe", "inherit"], windowsHide: true, windowsVerbatimArguments: true });
  let output = "";
  environmentProcess.stdout.setEncoding("utf8");
  environmentProcess.stdout.on("data", (chunk) => { output += chunk; });
  const environmentCode = await new Promise((resolve) => environmentProcess.once("exit", (code) => resolve(code ?? 1)));
  if (environmentCode !== 0) return process.env;
  const environment = { ...process.env };
  for (const line of output.split(/\r?\n/)) {
    const separator = line.indexOf("=");
    if (separator > 0) environment[line.slice(0, separator)] = line.slice(separator + 1);
  }
  return environment;
}

const manifestUrl = `https://github.com/waleed-khan13/socium/releases/latest/download/socium-manifest.json`;
const cargoHome = process.env.CARGO_HOME || path.join(os.homedir(), ".cargo");
const cargo = process.platform === "win32" ? path.join(cargoHome, "bin", "cargo.exe") : path.join(cargoHome, "bin", "cargo");
const buildEnvironment = {
  ...(await windowsBuildEnvironment()),
  SOCIUM_BUNDLE_PATH: archive,
  SOCIUM_BUNDLE_SHA256: fragment.sha256,
  SOCIUM_RELEASE_TARGET: target,
  SOCIUM_RELEASE_VERSION: version,
  SOCIUM_RELEASE_MANIFEST: manifestUrl,
};
await run(cargo, ["build", "--release", "--locked", "--manifest-path", path.join(projectRoot, "native", "installer", "Cargo.toml")], { env: buildEnvironment });

const binaryName = process.platform === "win32" ? "socium-native-installer.exe" : "socium-native-installer";
const binary = path.join(projectRoot, "native", "installer", "target", "release", binaryName);
await access(binary);
const installerName = nativeInstallerFileName(version, target);
const installerPath = path.join(releaseDirectory, installerName);
await rm(installerPath, { force: true });

if (target.startsWith("win32-")) {
  await cp(binary, installerPath);
} else if (target.startsWith("darwin-")) {
  const appRoot = path.join(releaseDirectory, "installer-staging", target, "Socium.app");
  const contents = path.join(appRoot, "Contents");
  await rm(path.dirname(appRoot), { recursive: true, force: true });
  await mkdir(path.join(contents, "MacOS"), { recursive: true });
  await cp(binary, path.join(contents, "MacOS", "Socium"));
  await chmod(path.join(contents, "MacOS", "Socium"), 0o755);
  await writeFile(path.join(contents, "Info.plist"), `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleDisplayName</key><string>Socium</string>
<key>CFBundleExecutable</key><string>Socium</string>
<key>CFBundleIdentifier</key><string>dev.socium.app</string>
<key>CFBundleName</key><string>Socium</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>${version}</string>
<key>CFBundleVersion</key><string>${version}</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
</dict></plist>\n`);
  await run("codesign", ["--force", "--deep", "--sign", "-", appRoot]);
  const dmgRoot = path.join(releaseDirectory, "installer-staging", target, "dmg");
  await mkdir(dmgRoot, { recursive: true });
  await cp(appRoot, path.join(dmgRoot, "Socium.app"), { recursive: true });
  await run("ln", ["-s", "/Applications", path.join(dmgRoot, "Applications")]);
  await run("hdiutil", ["create", "-volname", "Socium", "-srcfolder", dmgRoot, "-ov", "-format", "UDZO", installerPath]);
} else if (target.startsWith("linux-")) {
  const appDir = path.join(releaseDirectory, "installer-staging", target, "Socium.AppDir");
  await rm(appDir, { recursive: true, force: true });
  await mkdir(path.join(appDir, "usr", "bin"), { recursive: true });
  await cp(binary, path.join(appDir, "AppRun"));
  await chmod(path.join(appDir, "AppRun"), 0o755);
  await cp(path.join(projectRoot, "public", "brand", "socium-app-icon.svg"), path.join(appDir, "socium.svg"));
  await writeFile(path.join(appDir, "socium.desktop"), `[Desktop Entry]\nType=Application\nName=Socium\nComment=Local-first AI social publishing\nExec=Socium\nIcon=socium\nCategories=Office;Network;\nTerminal=false\n`);
  const architecture = target.endsWith("arm64") ? "aarch64" : "x86_64";
  const expectedToolSha = architecture === "aarch64"
    ? "f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158"
    : "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0";
  const tool = path.join(releaseDirectory, `appimagetool-${architecture}.AppImage`);
  const response = await fetch(`https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-${architecture}.AppImage`);
  if (!response.ok) throw new Error(`Could not download pinned appimagetool (${response.status}).`);
  await writeFile(tool, Buffer.from(await response.arrayBuffer()), { flag: "wx" }).catch(async (error) => {
    if (error.code !== "EEXIST") throw error;
  });
  if ((await sha256(tool)) !== expectedToolSha) throw new Error("Pinned appimagetool checksum verification failed.");
  await chmod(tool, 0o755);
  const runtimeExpectedSha = architecture === "aarch64"
    ? "7d5d772b7c32f0c84caf0a452a3072a5709027d7eac5856feb89a7a7a8881372"
    : "1cc49bcf1e2ccd593c379adb17c9f85a36d619088296504de95b1d06215aebbf";
  const appImageRuntime = path.join(releaseDirectory, `appimage-runtime-${architecture}`);
  const runtimeResponse = await fetch(`https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${architecture}`);
  if (!runtimeResponse.ok) throw new Error(`Could not download the pinned AppImage runtime (${runtimeResponse.status}).`);
  await writeFile(appImageRuntime, Buffer.from(await runtimeResponse.arrayBuffer()), { flag: "wx" }).catch(async (error) => {
    if (error.code !== "EEXIST") throw error;
  });
  if ((await sha256(appImageRuntime)) !== runtimeExpectedSha) throw new Error("Pinned AppImage runtime checksum verification failed.");
  await run(tool, ["--appimage-extract-and-run", "--runtime-file", appImageRuntime, appDir, installerPath], { env: { ...process.env, ARCH: architecture, VERSION: version } });
}

const installerSha256 = await sha256(installerPath);
await writeFile(path.join(releaseDirectory, `socium-installer-${target}.json`), `${JSON.stringify({ target, version, file: installerName, sha256: installerSha256 }, null, 2)}\n`);
console.log(`Built ${installerPath}`);
console.log(`SHA-256 ${installerSha256}`);
