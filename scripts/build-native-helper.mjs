import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

if (process.platform !== "win32") {
  console.log("The Socium native helper is Windows-only; nothing to build on this platform.");
  process.exit(0);
}

const projectRoot = process.cwd();
const manifest = path.join(projectRoot, "native", "windows-helper", "Cargo.toml");
const cargoHome = process.env.CARGO_HOME || path.join(os.homedir(), ".cargo");
const cargo = path.join(cargoHome, "bin", "cargo.exe");

try {
  await access(cargo);
} catch {
  throw new Error("Rust is not installed. Install rustup from https://rustup.rs and run this command again.");
}

async function windowsBuildEnvironment() {
  const programFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  const vswhere = path.join(programFilesX86, "Microsoft Visual Studio", "Installer", "vswhere.exe");
  try {
    await access(vswhere);
  } catch {
    return process.env;
  }
  const query = spawn(
    vswhere,
    ["-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
    { stdio: ["ignore", "pipe", "ignore"], windowsHide: true },
  );
  let installationPath = "";
  query.stdout.setEncoding("utf8");
  query.stdout.on("data", (chunk) => { installationPath += chunk; });
  const queryCode = await new Promise((resolve) => query.once("exit", (code) => resolve(code ?? 1)));
  if (queryCode !== 0 || !installationPath.trim()) return process.env;
  const vcvars = path.join(
    installationPath.trim(),
    "VC",
    "Auxiliary",
    "Build",
    process.arch === "arm64" ? "vcvarsarm64.bat" : "vcvars64.bat",
  );
  const environmentProcess = spawn("cmd.exe", ["/d", "/c", `call "${vcvars}" >nul && set`], {
    stdio: ["ignore", "pipe", "inherit"],
    windowsHide: true,
    windowsVerbatimArguments: true,
  });
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

const child = spawn(cargo, ["build", "--release", "--locked", "--manifest-path", manifest], {
  cwd: projectRoot,
  env: await windowsBuildEnvironment(),
  stdio: "inherit",
  windowsHide: true,
});
const exitCode = await new Promise((resolve, reject) => {
  child.once("error", reject);
  child.once("exit", (code) => resolve(code ?? 1));
});
if (exitCode !== 0) process.exit(exitCode);
console.log(path.join(projectRoot, "native", "windows-helper", "target", "release", "socium-windows-helper.exe"));
