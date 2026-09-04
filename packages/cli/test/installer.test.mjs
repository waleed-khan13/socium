import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { once } from "node:events";
import { createReadStream } from "node:fs";
import { chmod, mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import * as tar from "tar";

import { main } from "../src/cli.mjs";
import { createBackup, listBackups, restoreBackup } from "../src/backup.mjs";
import { CLI_VERSION } from "../src/constants.mjs";
import { createDownloadReporter, formatDownloadProgress } from "../src/download-progress.mjs";
import { diagnose } from "../src/doctor.mjs";
import { installRelease, loadInstallation, registerBundledRuntime } from "../src/installation.mjs";
import { applyUpdate, compareVersions, terminateMigrationCheck } from "../src/lifecycle.mjs";
import { resolveAssetSource, validateManifest } from "../src/manifest.mjs";
import {
  autostartStatus,
  quoteWindowsArgument,
  setAutostart,
  windowsNativeHelperPath,
  writePortableLauncher,
} from "../src/native-integration.mjs";
import { sociumPaths, sociumRoot } from "../src/paths.mjs";
import { backendFileName, releaseTarget } from "../src/platform.mjs";
import { uninstall } from "../src/uninstall.mjs";
import { relocateStorage } from "../src/storage.mjs";

async function checksum(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

async function writeReleaseFixture({ root, target, version }) {
  const bundle = path.join(root, `bundle-${version}`);
  const backend = path.join(bundle, "backend", backendFileName(target.split("-")[0]));
  await mkdir(path.join(bundle, "web"), { recursive: true });
  await mkdir(path.dirname(backend), { recursive: true });
  await writeFile(path.join(bundle, "web", "server.js"), "// fixture\n");
  await writeFile(backend, "fixture\n");
  if (process.platform !== "win32") await chmod(backend, 0o755);
  await writeFile(
    path.join(bundle, "bundle.json"),
    JSON.stringify({ schemaVersion: 1, product: "socium", version, target }),
  );
  const archive = path.join(root, `bundle-${version}.tar.gz`);
  await tar.c({ cwd: bundle, file: archive, gzip: true }, ["bundle.json", "backend", "web"]);
  const manifest = path.join(root, `manifest-${version}.json`);
  await writeFile(
    manifest,
    JSON.stringify({
      schemaVersion: 1,
      product: "socium",
      version,
      assets: { [target]: { url: path.basename(archive), sha256: await checksum(archive) } },
    }),
  );
  return { archive, manifest, version };
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "socium-cli-"));
  const target = releaseTarget();
  const release = await writeReleaseFixture({ root, target, version: "1.0.5" });
  return { ...release, paths: sociumPaths({ environment: { SOCIUM_HOME: path.join(root, "home") } }), root, target };
}

test("maps application data to native OS locations", () => {
  assert.equal(
    sociumRoot({ platform: "win32", homeDirectory: "C:\\Users\\Ada", environment: { LOCALAPPDATA: "C:\\Local" } }),
    path.resolve("C:\\Local", "Socium"),
  );
  assert.equal(
    sociumRoot({ platform: "darwin", homeDirectory: "/Users/ada", environment: {} }),
    path.resolve("/Users/ada/Library/Application Support/Socium"),
  );
  assert.equal(
    sociumRoot({ platform: "linux", homeDirectory: "/home/ada", environment: {} }),
    path.resolve("/home/ada/.local/share/socium"),
  );
});

test("maps the active Windows runtime to the native helper without PowerShell", () => {
  const installation = { runtimePath: "C:\\Socium\\runtime" };
  assert.equal(
    windowsNativeHelperPath(installation),
    path.join(installation.runtimePath, "native", "socium-windows-helper.exe"),
  );
  assert.equal(quoteWindowsArgument("C:\\Socium Data\\launch.mjs"), '"C:\\Socium Data\\launch.mjs"');
});

test("force-stops a migration check that ignores graceful termination", async () => {
  const signals = [];
  const child = {
    exitCode: null,
    signalCode: null,
    kill(signal) {
      signals.push(signal);
      if (signal === "SIGKILL") this.signalCode = signal;
      return true;
    },
  };
  await terminateMigrationCheck(child, { platform: "linux", gracefulTimeoutMs: 0, forceTimeoutMs: 100 });
  assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
});

test("recognizes a migration check that exits from a graceful Unix signal", async () => {
  const signals = [];
  const child = {
    exitCode: null,
    signalCode: null,
    kill(signal) {
      signals.push(signal);
      this.signalCode = signal;
      return true;
    },
  };
  await terminateMigrationCheck(child, { platform: "darwin", gracefulTimeoutMs: 100 });
  assert.deepEqual(signals, ["SIGTERM"]);
});

test("rejects application and durable storage roots that are unsafe to purge", async (context) => {
  assert.throws(
    () => sociumRoot({ environment: { SOCIUM_HOME: path.parse(process.cwd()).root }, homeDirectory: os.homedir() }),
    /cannot be a drive/,
  );
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  await assert.rejects(
    installRelease({
      manifestSource: current.manifest,
      paths: current.paths,
      target: current.target,
      dataDirectory: path.parse(current.root).root,
      modelsDirectory: path.join(current.root, "models-safe"),
      log() {},
    }),
    /Data directory cannot be/,
  );
});

test("does not claim an existing non-empty model directory", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const modelsDirectory = path.join(current.root, "shared-models");
  await mkdir(modelsDirectory, { recursive: true });
  await writeFile(path.join(modelsDirectory, "unrelated.gguf"), "not managed by Socium");
  await assert.rejects(
    installRelease({
      manifestSource: current.manifest,
      paths: current.paths,
      target: current.target,
      modelsDirectory,
      log() {},
    }),
    /Model directory is not empty/,
  );
});

test("registers an embedded native-installer runtime without downloading it", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const runtimePath = path.join(current.paths.runtimesDirectory, "1.3.0", current.target);
  const platform = current.target.split("-")[0];
  const backend = path.join(runtimePath, "backend", backendFileName(platform));
  const node = path.join(runtimePath, "bin", platform === "win32" ? "node.exe" : "node");
  await mkdir(path.join(runtimePath, "web"), { recursive: true });
  await mkdir(path.join(runtimePath, "controller"), { recursive: true });
  await mkdir(path.dirname(backend), { recursive: true });
  await mkdir(path.dirname(node), { recursive: true });
  await writeFile(path.join(runtimePath, "web", "server.js"), "// fixture\n");
  await writeFile(path.join(runtimePath, "controller", "controller.mjs"), "// fixture\n");
  await writeFile(path.join(runtimePath, "controller", "managed-cli.mjs"), "// fixture\n");
  await writeFile(path.join(runtimePath, "controller", "offline-install.mjs"), "// fixture\n");
  await writeFile(backend, "fixture\n");
  await writeFile(node, "fixture\n");
  if (platform === "win32") {
    const helper = path.join(runtimePath, "native", "socium-windows-helper.exe");
    await mkdir(path.dirname(helper), { recursive: true });
    await writeFile(helper, "fixture\n");
  }
  await writeFile(
    path.join(runtimePath, "bundle.json"),
    JSON.stringify({ schemaVersion: 3, product: "socium", version: "1.3.0", target: current.target }),
  );

  const installation = await registerBundledRuntime({
    runtimePath,
    version: "1.3.0",
    target: current.target,
    manifestSource: "https://github.com/waleed-khan13/socium/releases/latest/download/socium-manifest.json",
    paths: current.paths,
  });

  assert.equal(installation.runtimePath, runtimePath);
  assert.equal((await loadInstallation(current.paths)).version, "1.3.0");
  assert.match(await readFile(path.join(installation.dataDirectory, ".socium-storage.json"), "utf8"), /socium/);
  assert.match(await readFile(path.join(installation.modelsDirectory, ".socium-models.json"), "utf8"), /socium-models/);
});

test("supports conventional version commands", async () => {
  for (const argument of ["version", "--version", "-v"]) {
    const output = [];
    assert.equal(await main([argument], { log: (value) => output.push(value) }), 0);
    assert.deepEqual(output, [CLI_VERSION]);
  }
});

test("prints help through the named command", async () => {
  const output = [];
  assert.equal(await main(["help"], { log: (value) => output.push(value) }), 0);
  assert.match(output.join("\n"), /socium storage move/);
});

test("formats and renders terminal download progress", () => {
  const line = formatDownloadProgress({
    downloadedBytes: 1024 * 1024,
    totalBytes: 2 * 1024 * 1024,
    elapsedMs: 1000,
    status: "progress",
  });
  assert.match(line, /50%/);
  assert.match(line, /1\.0 \/ 2\.0 MB/);
  assert.match(line, /1\.0 MB\/s/);
  assert.match(line, /ETA 00:01/);

  const writes = [];
  const reporter = createDownloadReporter({
    stream: { isTTY: true, write: (value) => writes.push(value) },
    now: () => 1000,
    updateIntervalMs: 250,
  });
  reporter({ downloadedBytes: 0, totalBytes: 100, elapsedMs: 0, status: "start" });
  reporter({ downloadedBytes: 1, totalBytes: 100, elapsedMs: 1000, status: "progress" });
  reporter({ downloadedBytes: 2, totalBytes: 100, elapsedMs: 1000, status: "progress" });
  reporter({ downloadedBytes: 50, totalBytes: 100, elapsedMs: 1000, status: "progress" });
  reporter({ downloadedBytes: 100, totalBytes: 100, elapsedMs: 2000, status: "complete" });
  assert.match(writes.join(""), /1%/);
  assert.match(writes.join(""), /2%/);
  assert.match(writes.join(""), /50%/);
  assert.match(writes.join(""), /100%/);
  assert.equal(writes.at(-1), "\n");
});

test("logs every download percentage when output is not interactive", () => {
  const messages = [];
  const reporter = createDownloadReporter({
    stream: { isTTY: false },
    log: (value) => messages.push(value),
    now: () => 1000,
    updateIntervalMs: 0,
  });
  for (const percentage of [0, 1, 2, 3, 100]) {
    reporter({
      downloadedBytes: percentage,
      totalBytes: 100,
      elapsedMs: percentage * 100,
      status: percentage === 0 ? "start" : percentage === 100 ? "complete" : "progress",
    });
  }
  assert.equal(messages.length, 5);
  assert.match(messages[0], /0%/);
  assert.match(messages[1], /1%/);
  assert.match(messages[2], /2%/);
  assert.match(messages[3], /3%/);
  assert.match(messages[4], /100%/);
});

test("compares stable release versions", () => {
  assert.equal(compareVersions("1.0.5", "1.1.0"), -1);
  assert.equal(compareVersions("2.0.0", "1.9.9"), 1);
  assert.equal(compareVersions("1.0.5", "1.0.5"), 0);
});

test("creates checksummed backups and restores without deleting the previous data", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const businessFile = path.join(installed.dataDirectory, "business.json");
  await writeFile(businessFile, "before-update");
  const backup = await createBackup({ paths: current.paths, log() {} });
  assert.equal((await listBackups({ paths: current.paths })).length, 1);
  await writeFile(businessFile, "changed");
  const restored = await restoreBackup({ backupPath: backup.path, paths: current.paths, log() {} });
  assert.equal(await readFile(businessFile, "utf8"), "before-update");
  assert.match(restored.preservedDirectory, /before-restore/);
  assert.equal(await readFile(path.join(restored.preservedDirectory, "business.json"), "utf8"), "changed");
});

test("removes incomplete backup artifacts when the selected drive is full", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const noSpace = Object.assign(new Error("disk full"), { code: "ENOSPC" });
  await assert.rejects(
    createBackup({ paths: current.paths, archive: async () => { throw noSpace; }, log() {} }),
    /selected drive is full/,
  );
  assert.deepEqual(await listBackups({ paths: current.paths }), []);
  assert.equal((await readdir(current.paths.dataDirectory)).some((item) => item.startsWith(".socium-backup-")), false);
  assert.equal((await readdir(current.paths.backupsDirectory)).some((item) => item.endsWith(".partial")), false);
});

test("creates a stable launcher that resolves the active runtime after updates", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const bundledNode = path.join(installed.runtimePath, "bin", process.platform === "win32" ? "node.exe" : "node");
  await mkdir(path.dirname(bundledNode), { recursive: true });
  await writeFile(bundledNode, "fixture node");

  const launcher = await writePortableLauncher(current.paths, installed);
  const script = await readFile(launcher.script, "utf8");
  assert.equal(await readFile(launcher.node, "utf8"), "fixture node");
  assert.match(script, /installation\.runtimePath/);
  assert.match(script, /controller\.mjs/);
  assert.doesNotMatch(script, new RegExp(installed.runtimePath.replaceAll("\\", "\\\\")));
});

test("uses the bundled Socium icon for Windows shortcuts", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const bundledNode = path.join(installed.runtimePath, "bin", "node.exe");
  await mkdir(path.dirname(bundledNode), { recursive: true });
  await writeFile(bundledNode, "fixture node");

  const launcher = await writePortableLauncher(current.paths, installed, "win32");
  assert.equal(launcher.icon, path.join(installed.runtimePath, "native", "socium.ico"));
});

test("macOS and Linux autostart records follow the stable active-runtime launcher", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  for (const platform of ["darwin", "linux"]) {
    const bundledNode = path.join(installed.runtimePath, "bin", "node");
    await mkdir(path.dirname(bundledNode), { recursive: true });
    await writeFile(bundledNode, "fixture node");
    const homeDirectory = path.join(current.root, `native-${platform}`);
    const environment = { XDG_CONFIG_HOME: path.join(homeDirectory, ".config") };
    const enabled = await setAutostart({ paths: current.paths, enabled: true, platform, environment, homeDirectory });
    const record = await readFile(enabled.path, "utf8");
    assert.match(record, /launcher/);
    assert.doesNotMatch(record, new RegExp(installed.runtimePath.replaceAll("\\", "\\\\")));
    assert.equal((await autostartStatus({ platform, environment, homeDirectory })).enabled, true);
    await setAutostart({ paths: current.paths, enabled: false, platform, environment, homeDirectory });
    assert.equal((await autostartStatus({ platform, environment, homeDirectory })).enabled, false);
  }
});

test("migration failure restores the previous runtime and durable backup", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const businessFile = path.join(installed.dataDirectory, "business.json");
  await writeFile(businessFile, "before-update");
  const next = await writeReleaseFixture({ root: current.root, target: current.target, version: "1.1.0" });

  await assert.rejects(
    applyUpdate({
      manifestSource: next.manifest,
      paths: current.paths,
      target: current.target,
      migrationVerifier: async () => {
        await writeFile(businessFile, "failed-migration");
        throw new Error("migration health check failed");
      },
      log() {},
    }),
    /migration health check failed/,
  );
  assert.equal((await loadInstallation(current.paths)).version, "1.0.5");
  assert.equal(await readFile(businessFile, "utf8"), "before-update");
});

test("interrupted update leaves the active runtime and data unchanged", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const businessFile = path.join(installed.dataDirectory, "business.json");
  await writeFile(businessFile, "durable-data");
  const next = await writeReleaseFixture({ root: current.root, target: current.target, version: "1.1.0" });
  const manifest = JSON.parse(await readFile(next.manifest, "utf8"));
  manifest.assets[current.target].sha256 = "0".repeat(64);
  await writeFile(next.manifest, JSON.stringify(manifest));

  await assert.rejects(
    applyUpdate({ manifestSource: next.manifest, paths: current.paths, target: current.target, migrationVerifier: async () => {}, log() {} }),
    /checksum verification failed/,
  );
  assert.equal((await loadInstallation(current.paths)).runtimePath, installed.runtimePath);
  assert.equal(await readFile(businessFile, "utf8"), "durable-data");
  assert.equal((await readdir(current.paths.downloadsDirectory)).length, 0);
});

test("rejects wrong-product and path-like release metadata", () => {
  const target = releaseTarget();
  const asset = { url: "bundle.tar.gz", sha256: "a".repeat(64) };
  assert.throws(
    () => validateManifest({ schemaVersion: 1, product: "another-product", version: "1.0.5", assets: { [target]: asset } }, target),
    /unexpected product/,
  );
  assert.throws(
    () => validateManifest({ schemaVersion: 1, product: "socium", version: "..", assets: { [target]: asset } }, target),
    /invalid version/,
  );
  assert.throws(
    () => resolveAssetSource("file:///private/archive.tar.gz", "https://releases.example/manifest.json"),
    /insecure release URL/,
  );
});

test("installs a checksummed platform bundle and diagnoses the runtime", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const messages = [];
  const installed = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    log: (message) => messages.push(message),
  });
  assert.equal(installed.version, "1.0.5");
  assert.equal((await loadInstallation(current.paths)).target, current.target);
  assert.match(await readFile(path.join(installed.runtimePath, "bundle.json"), "utf8"), /socium/);
  assert.ok(messages.some((message) => message.startsWith("Installed Socium")));

  const report = await diagnose({ paths: current.paths, webPort: 39171, apiPort: 39172 });
  assert.equal(report.ok, true);
  assert.ok(report.checks.some((check) => check.name === "FastAPI runtime" && check.ok));
});

test("rejects a bundle when its checksum is not trusted", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const manifest = JSON.parse(await readFile(current.manifest, "utf8"));
  manifest.assets[current.target].sha256 = "0".repeat(64);
  await writeFile(current.manifest, JSON.stringify(manifest));
  await assert.rejects(
    installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} }),
    /checksum verification failed/,
  );
  assert.equal(await loadInstallation(current.paths), null);
});

test("keeps slow downloads alive while bytes continue to arrive", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const archive = await readFile(current.archive);
  const chunkSize = Math.ceil(archive.length / 40);
  const server = createServer((_request, response) => {
    response.writeHead(200, { "content-length": archive.length, "content-type": "application/gzip" });
    let offset = 0;
    const interval = setInterval(() => {
      const next = Math.min(offset + chunkSize, archive.length);
      response.write(archive.subarray(offset, next));
      offset = next;
      if (offset === archive.length) {
        clearInterval(interval);
        response.end();
      }
    }, 50);
    response.on("close", () => clearInterval(interval));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  context.after(() => new Promise((resolve) => server.close(resolve)));

  const previous = process.env.SOCIUM_ALLOW_INSECURE_DOWNLOADS;
  process.env.SOCIUM_ALLOW_INSECURE_DOWNLOADS = "1";
  context.after(() => {
    if (previous === undefined) delete process.env.SOCIUM_ALLOW_INSECURE_DOWNLOADS;
    else process.env.SOCIUM_ALLOW_INSECURE_DOWNLOADS = previous;
  });

  const address = server.address();
  const manifest = JSON.parse(await readFile(current.manifest, "utf8"));
  manifest.assets[current.target].url = `http://127.0.0.1:${address.port}/bundle.tar.gz`;
  await writeFile(current.manifest, JSON.stringify(manifest));

  const progressEvents = [];

  const installed = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    downloadIdleTimeoutMs: 250,
    onDownloadProgress: (progress) => progressEvents.push(progress),
    log() {},
  });
  assert.equal(installed.target, current.target);
  assert.equal(progressEvents[0].status, "start");
  assert.equal(progressEvents[0].totalBytes, archive.length);
  assert.ok(progressEvents.some((progress) => progress.status === "progress" && progress.downloadedBytes > 0));
  assert.equal(progressEvents.at(-1).status, "complete");
  assert.equal(progressEvents.at(-1).downloadedBytes, archive.length);
});

test("uninstall preserves data unless purge is explicit", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  const database = path.join(current.paths.dataDirectory, "socium.db");
  await writeFile(database, "durable data");

  await assert.rejects(uninstall({ paths: current.paths }), /requires --yes/);
  const result = await uninstall({ paths: current.paths, confirmed: true });
  assert.equal(result.preservedData, true);
  assert.equal(await readFile(database, "utf8"), "durable data");
  assert.equal(await stat(current.paths.launcherDirectory).then(() => true, () => false), false);

  await uninstall({ paths: current.paths, confirmed: true, purgeData: true });
  await assert.rejects(readFile(database, "utf8"), /ENOENT/);
});

test("keeps custom durable data and model locations across runtime updates", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const dataDirectory = path.join(current.root, "durable", "business-data");
  const modelsDirectory = path.join(current.root, "ai-models");

  const installed = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    dataDirectory,
    modelsDirectory,
    log() {},
  });
  assert.equal(installed.dataDirectory, path.resolve(dataDirectory));
  assert.equal(installed.modelsDirectory, path.resolve(modelsDirectory));
  assert.match(await readFile(path.join(dataDirectory, ".socium-storage.json"), "utf8"), /socium/);

  const updated = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    force: true,
    log() {},
  });
  assert.equal(updated.dataDirectory, installed.dataDirectory);
  assert.equal(updated.modelsDirectory, installed.modelsDirectory);
});

test("moves storage with checksum verification and preserves the source", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    log() {},
  });
  await writeFile(path.join(installed.dataDirectory, "socium.db"), "durable database");
  await writeFile(path.join(installed.modelsDirectory, "model.gguf"), "local model");
  const nextData = path.join(current.root, "moved-data");
  const nextModels = path.join(current.root, "moved-models");

  const result = await relocateStorage({ paths: current.paths, dataDirectory: nextData, modelsDirectory: nextModels });
  assert.equal(result.sourcePreserved, true);
  assert.equal(await readFile(path.join(nextData, "socium.db"), "utf8"), "durable database");
  assert.equal(await readFile(path.join(nextModels, "model.gguf"), "utf8"), "local model");
  assert.equal(await readFile(path.join(installed.dataDirectory, "socium.db"), "utf8"), "durable database");
  assert.equal((await loadInstallation(current.paths)).dataDirectory, path.resolve(nextData));
});

test("moves storage into empty folders selected by a native folder picker", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({
    manifestSource: current.manifest,
    paths: current.paths,
    target: current.target,
    log() {},
  });
  await writeFile(path.join(installed.dataDirectory, "socium.db"), "durable database");
  const nextData = path.join(current.root, "selected-data");
  const nextModels = path.join(current.root, "selected-models");
  await mkdir(nextData, { recursive: true });
  await mkdir(nextModels, { recursive: true });

  await relocateStorage({ paths: current.paths, dataDirectory: nextData, modelsDirectory: nextModels });

  assert.equal(await readFile(path.join(nextData, "socium.db"), "utf8"), "durable database");
  assert.equal((await loadInstallation(current.paths)).modelsDirectory, path.resolve(nextModels));
});

test("reports a selected data drive as unavailable instead of creating a blank location", async (context) => {
  const current = await fixture();
  context.after(() => rm(current.root, { recursive: true, force: true }));
  const installed = await installRelease({ manifestSource: current.manifest, paths: current.paths, target: current.target, log() {} });
  await rm(installed.dataDirectory, { recursive: true, force: true });

  const report = await diagnose({ paths: current.paths, webPort: 39173, apiPort: 39174 });
  const dataCheck = report.checks.find((check) => check.name === "Data directory");
  assert.equal(dataCheck.ok, false);
  assert.equal(await stat(installed.dataDirectory).then(() => true, () => false), false);
});
