import {
  CLI_VERSION,
  DEFAULT_API_PORT,
  DEFAULT_MANIFEST_URL,
  DEFAULT_WEB_PORT,
} from "./constants.mjs";
import { diagnose } from "./doctor.mjs";
import { createDownloadReporter } from "./download-progress.mjs";
import { installRelease } from "./installation.mjs";
import { sociumPaths } from "./paths.mjs";
import { startRuntime } from "./runtime.mjs";
import { relocateStorage } from "./storage.mjs";
import { uninstall } from "./uninstall.mjs";

const helpText = `Socium ${CLI_VERSION}

Usage:
  socium onboard [--manifest URL] [--data-dir PATH] [--models-dir PATH] [--install-only] [--no-open]
  socium start [--port 3000] [--api-port 8000] [--no-open] [--labs]
  socium run [--port 3000] [--api-port 8000] [--no-open] [--labs]  (alias for start)
  socium update [--manifest URL] [--force]
  socium doctor [--json]
  socium storage move [--data-dir PATH] [--models-dir PATH]
  socium uninstall --yes [--purge-data]
  socium version

Environment:
  SOCIUM_HOME                 Override the application data/runtime root.
  SOCIUM_RELEASE_MANIFEST     Override the official release manifest URL.
  SOCIUM_DATA_DIR             Default durable data location for first install.
  SOCIUM_MODELS_DIR           Default local AI model location for first install.
`;

function parseArguments(argv) {
  const command = argv[0] || "help";
  const values = new Map();
  const flags = new Set();
  let subcommand;
  let startIndex = 1;
  if (command === "storage" && argv[1] && !argv[1].startsWith("--")) {
    subcommand = argv[1];
    startIndex = 2;
  }
  for (let index = startIndex; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) throw new Error(`Unexpected argument: ${value}`);
    if (["--manifest", "--port", "--api-port", "--data-dir", "--models-dir"].includes(value)) {
      const next = argv[index + 1];
      if (!next || next.startsWith("--")) throw new Error(`${value} requires a value.`);
      values.set(value, next);
      index += 1;
    } else {
      flags.add(value);
    }
  }
  return { command, subcommand, flags, values };
}

function parsePort(value, fallback, name) {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) throw new Error(`${name} must be 1-65535.`);
  return parsed;
}

function manifestSource(arguments_) {
  return (
    arguments_.values.get("--manifest") || process.env.SOCIUM_RELEASE_MANIFEST || DEFAULT_MANIFEST_URL
  );
}

function printDoctor(result, log) {
  log(`Socium home: ${result.root}`);
  for (const check of result.checks) log(`${check.ok ? "PASS" : check.advisory ? "INFO" : "FAIL"}  ${check.name}: ${check.detail}`);
  log(result.ok ? "Doctor completed successfully." : "Doctor found blocking problems.");
}

export async function main(argv, { log = console.log, error = console.error, output = process.stdout } = {}) {
  try {
    const arguments_ = parseArguments(argv);
    const paths = sociumPaths();
    const webPort = parsePort(arguments_.values.get("--port"), DEFAULT_WEB_PORT, "--port");
    const apiPort = parsePort(arguments_.values.get("--api-port"), DEFAULT_API_PORT, "--api-port");

    if (["help", "--help", "-h"].includes(arguments_.command)) {
      log(helpText);
      return 0;
    }
    if (["version", "--version", "-v"].includes(arguments_.command)) {
      log(CLI_VERSION);
      return 0;
    }
    if (arguments_.command === "doctor") {
      const result = await diagnose({ paths, webPort, apiPort });
      if (arguments_.flags.has("--json")) log(JSON.stringify(result, null, 2));
      else printDoctor(result, log);
      return result.ok ? 0 : 1;
    }
    if (arguments_.command === "storage") {
      if (arguments_.subcommand !== "move") throw new Error("Usage: socium storage move [--data-dir PATH] [--models-dir PATH]");
      if (!arguments_.values.has("--data-dir") && !arguments_.values.has("--models-dir")) {
        throw new Error("Choose --data-dir, --models-dir, or both.");
      }
      const result = await relocateStorage({
        paths,
        dataDirectory: arguments_.values.get("--data-dir"),
        modelsDirectory: arguments_.values.get("--models-dir"),
      });
      log(`Storage activated at ${result.installation.dataDirectory}`);
      log("The previous locations were preserved. Confirm Socium starts correctly before removing them manually.");
      return 0;
    }
    if (arguments_.command === "uninstall") {
      const result = await uninstall({
        paths,
        confirmed: arguments_.flags.has("--yes"),
        purgeData: arguments_.flags.has("--purge-data"),
      });
      log(result.preservedData ? `Runtime removed. Local data was preserved at ${result.dataDirectory}` : "Runtime and local data removed.");
      return 0;
    }
    if (arguments_.command === "update") {
      await installRelease({
        manifestSource: manifestSource(arguments_),
        paths,
        force: arguments_.flags.has("--force"),
        dataDirectory: arguments_.values.get("--data-dir") || process.env.SOCIUM_DATA_DIR,
        modelsDirectory: arguments_.values.get("--models-dir") || process.env.SOCIUM_MODELS_DIR,
        onDownloadProgress: createDownloadReporter({ stream: output, log }),
        log,
      });
      return 0;
    }
    if (arguments_.command === "onboard") {
      await installRelease({
        manifestSource: manifestSource(arguments_),
        paths,
        force: arguments_.flags.has("--force"),
        dataDirectory: arguments_.values.get("--data-dir") || process.env.SOCIUM_DATA_DIR,
        modelsDirectory: arguments_.values.get("--models-dir") || process.env.SOCIUM_MODELS_DIR,
        onDownloadProgress: createDownloadReporter({ stream: output, log }),
        log,
      });
      if (arguments_.flags.has("--install-only")) return 0;
      const result = await startRuntime({
        paths,
        webPort,
        apiPort,
        shouldOpenBrowser: !arguments_.flags.has("--no-open"),
        labsEnabled: arguments_.flags.has("--labs"),
        log,
      });
      return result.exitCode ?? 0;
    }
    if (["start", "run"].includes(arguments_.command)) {
      const result = await startRuntime({
        paths,
        webPort,
        apiPort,
        shouldOpenBrowser: !arguments_.flags.has("--no-open"),
        labsEnabled: arguments_.flags.has("--labs"),
        log,
      });
      return result.exitCode ?? 0;
    }

    throw new Error(`Unknown command: ${arguments_.command}\n\n${helpText}`);
  } catch (caught) {
    error(caught instanceof Error ? caught.message : String(caught));
    return 1;
  }
}
