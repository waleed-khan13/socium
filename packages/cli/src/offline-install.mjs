import path from "node:path";

import { registerBundledRuntime } from "./installation.mjs";
import { installNativeIntegration, setAutostart, writePortableLauncher } from "./native-integration.mjs";
import { sociumPaths } from "./paths.mjs";

function value(name) {
  const index = process.argv.indexOf(name);
  if (index < 0) return undefined;
  const result = process.argv[index + 1];
  if (!result || result.startsWith("--")) throw new Error(`${name} requires a value.`);
  return result;
}

const runtimePath = path.resolve(value("--runtime-path") || "");
const version = value("--version");
const target = value("--target");
const manifestSource = value("--manifest");
const paths = sociumPaths();

const installation = await registerBundledRuntime({
  runtimePath,
  version,
  target,
  manifestSource,
  paths,
  dataDirectory: value("--data-dir"),
  modelsDirectory: value("--models-dir"),
});

if (process.platform === "win32") {
  await installNativeIntegration({
    paths,
    shortcuts: !process.argv.includes("--no-shortcuts"),
    autostart: process.argv.includes("--autostart"),
  });
} else {
  await writePortableLauncher(paths, installation);
  if (process.argv.includes("--autostart")) await setAutostart({ paths, enabled: true });
}

process.stdout.write(`${JSON.stringify({ ok: true, runtimePath: installation.runtimePath })}\n`);
