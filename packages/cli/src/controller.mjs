import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { startRuntime } from "./runtime.mjs";
import { sociumPaths } from "./paths.mjs";

function sleep(milliseconds) { return new Promise((resolve) => setTimeout(resolve, milliseconds)); }

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? Number(process.argv[index + 1]) : fallback;
  if (!Number.isInteger(value) || value < 1 || value > 65535) throw new Error(`${name} must be 1-65535.`);
  return value;
}

function launchWindowsTray(dataDirectory) {
  const lock = path.join(dataDirectory, ".socium-runtime.json");
  const escaped = lock.replaceAll("'", "''");
  const script = `Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing;$l=Get-Content -LiteralPath '${escaped}' -Raw|ConvertFrom-Json;$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Application;$n.Text=('Socium '+$l.version);$n.Visible=$true;$m=New-Object System.Windows.Forms.ContextMenuStrip;$status=$m.Items.Add(('Running Socium '+$l.version));$status.Enabled=$false;$open=$m.Items.Add('Open dashboard');$open.add_Click({try{$x=Get-Content -LiteralPath '${escaped}' -Raw|ConvertFrom-Json;Start-Process ('http://127.0.0.1:'+$x.webPort)}catch{}});$restart=$m.Items.Add('Restart');$restart.add_Click({try{$x=Get-Content -LiteralPath '${escaped}' -Raw|ConvertFrom-Json;$h=@{Authorization='Bearer '+$x.controlToken};Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:'+$x.controlPort+'/restart') -Headers $h|Out-Null}catch{}});$stop=$m.Items.Add('Stop');$stop.add_Click({try{$x=Get-Content -LiteralPath '${escaped}' -Raw|ConvertFrom-Json;$h=@{Authorization='Bearer '+$x.controlToken};Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:'+$x.controlPort+'/stop') -Headers $h|Out-Null}catch{};$n.Visible=$false;[System.Windows.Forms.Application]::Exit()});$exit=$m.Items.Add('Exit tray');$exit.add_Click({$n.Visible=$false;[System.Windows.Forms.Application]::Exit()});$n.ContextMenuStrip=$m;$n.add_DoubleClick({try{$x=Get-Content -LiteralPath '${escaped}' -Raw|ConvertFrom-Json;Start-Process ('http://127.0.0.1:'+$x.webPort)}catch{}});[System.Windows.Forms.Application]::Run();$n.Dispose()`;
  const child = spawn("powershell.exe", ["-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", script], { detached: true, stdio: "ignore", windowsHide: true });
  child.unref();
}

async function main() {
  const paths = sociumPaths();
  const wantsTray = process.argv.includes("--tray");
  const webPort = argument("--port", 3000);
  const apiPort = argument("--api-port", 8000);
  let firstRun = true;
  while (true) {
    const run = startRuntime({
      paths,
      webPort,
      apiPort,
      shouldOpenBrowser: firstRun && !process.argv.includes("--no-open"),
      labsEnabled: process.argv.includes("--labs"),
    });
    if (wantsTray && firstRun && process.platform === "win32") {
      for (let count = 0; count < 50; count += 1) {
        try {
          const installation = JSON.parse(await readFile(paths.installationFile, "utf8"));
          await readFile(path.join(installation.dataDirectory, ".socium-runtime.json"), "utf8");
          launchWindowsTray(installation.dataDirectory);
          break;
        } catch { await sleep(100); }
      }
    }
    const result = await run;
    if (result.action !== "restart") break;
    firstRun = false;
    await sleep(1_000);
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
