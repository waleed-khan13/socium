import { spawnSync } from "node:child_process";

function executable(name) {
  return name;
}

function run(command, args, options = {}) {
  const useShell = process.platform === "win32" && options.shell !== false;
  const shellCommand = useShell
    ? [command, ...args].map((value) => (/^[A-Za-z0-9_./:=@-]+$/.test(value) ? value : `"${value.replaceAll('"', '\\"')}"`)).join(" ")
    : command;
  const result = spawnSync(shellCommand, useShell ? [] : args, {
    cwd: process.cwd(),
    encoding: "utf8",
    shell: useShell,
    stdio: options.capture ? "pipe" : "inherit",
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (options.capture && result.stderr) process.stderr.write(result.stderr);
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}.`);
  }
  return options.capture ? result.stdout.trim() : "";
}

console.log("Auditing production JavaScript dependencies...");
run(executable("pnpm"), ["audit", "--prod", "--audit-level", "high"]);
run(executable("npm"), ["audit", "--omit=dev", "--audit-level=high", "--prefix", "packaging/web-runtime"]);

console.log("Auditing the synchronized Python environment...");
const sitePackages = run(
  executable("uv"),
  ["run", "--project", "backend", "python", "-c", "import site; print(site.getsitepackages()[0])"],
  { capture: true, shell: false },
);
run(executable("uvx"), ["pip-audit", "--path", sitePackages], { shell: false });
console.log("Security audit passed with no known vulnerabilities.");
