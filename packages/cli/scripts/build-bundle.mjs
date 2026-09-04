import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, chmod, cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as tar from "tar";

import {
  backendFileName,
  nativeHelperFileName,
  releaseTarget,
  supportedReleaseTargets,
} from "../src/platform.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = path.resolve(packageRoot, "../..");
const packageJson = JSON.parse(await readFile(path.join(packageRoot, "package.json"), "utf8"));

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function sha256(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) hash.update(chunk);
  return hash.digest("hex");
}

const target = argument("--target") || process.env.SOCIUM_RELEASE_TARGET || releaseTarget();
if (!supportedReleaseTargets().includes(target)) throw new Error(`Unsupported release target: ${target}`);

const version = packageJson.version;
const platform = target.split("-")[0];
const executableName = backendFileName(platform);
const backendBinary = path.resolve(
  process.env.SOCIUM_API_BINARY || path.join(projectRoot, "backend", "dist", executableName),
);
const helperName = nativeHelperFileName(platform);
const nativeHelperBinary = helperName
  ? path.resolve(
      process.env.SOCIUM_WINDOWS_HELPER_BINARY ||
        path.join(projectRoot, "native", "windows-helper", "target", "release", helperName),
    )
  : null;
const standaloneRoot = path.join(projectRoot, ".next", "standalone");
const portableModulesRoot = path.join(projectRoot, "packaging", "web-runtime", "node_modules");
const outputRoot = path.join(projectRoot, "release");
const stagingRoot = path.join(outputRoot, "staging", target);
const runtimeRoot = path.join(stagingRoot, "runtime");
const archiveName = `socium-${version}-${target}.tar.gz`;
const archivePath = path.join(outputRoot, archiveName);

if (!(await exists(path.join(standaloneRoot, "server.js")))) {
  throw new Error("Next.js standalone output is missing. Run `pnpm build` first.");
}
if (!(await exists(path.join(portableModulesRoot, "next", "package.json")))) {
  throw new Error("Portable web dependencies are missing. Run `pnpm runtime:sync` first.");
}
if (!(await exists(backendBinary))) {
  throw new Error(`Bundled FastAPI executable is missing: ${backendBinary}. Run \`pnpm backend:bundle\` first.`);
}
if (nativeHelperBinary && !(await exists(nativeHelperBinary))) {
  throw new Error(`Windows native helper is missing: ${nativeHelperBinary}. Run \`pnpm native:build\` first.`);
}

await rm(stagingRoot, { recursive: true, force: true });
await mkdir(path.join(runtimeRoot, "backend"), { recursive: true });
const standaloneModulesRoot = path.join(standaloneRoot, "node_modules");
await cp(standaloneRoot, path.join(runtimeRoot, "web"), {
  recursive: true,
  filter(source) {
    return source !== standaloneModulesRoot && !source.startsWith(`${standaloneModulesRoot}${path.sep}`);
  },
});
await cp(portableModulesRoot, path.join(runtimeRoot, "web", "node_modules"), {
  recursive: true,
  dereference: true,
});
await cp(path.join(projectRoot, ".next", "static"), path.join(runtimeRoot, "web", ".next", "static"), {
  recursive: true,
});
if (await exists(path.join(projectRoot, "public"))) {
  await cp(path.join(projectRoot, "public"), path.join(runtimeRoot, "web", "public"), { recursive: true });
}
await cp(backendBinary, path.join(runtimeRoot, "backend", executableName));
if (platform !== "win32") await chmod(path.join(runtimeRoot, "backend", executableName), 0o755);
if (nativeHelperBinary && helperName) {
  await mkdir(path.join(runtimeRoot, "native"), { recursive: true });
  await cp(nativeHelperBinary, path.join(runtimeRoot, "native", helperName));
  await cp(path.join(projectRoot, "src", "app", "favicon.ico"), path.join(runtimeRoot, "native", "socium.ico"));
}
await mkdir(path.join(runtimeRoot, "bin"), { recursive: true });
const nodeName = platform === "win32" ? "node.exe" : "node";
await cp(process.execPath, path.join(runtimeRoot, "bin", nodeName));
if (platform !== "win32") await chmod(path.join(runtimeRoot, "bin", nodeName), 0o755);
await mkdir(path.join(runtimeRoot, "controller"), { recursive: true });
await cp(path.join(packageRoot, "src"), path.join(runtimeRoot, "controller"), { recursive: true });
await cp(path.join(packageRoot, "node_modules"), path.join(runtimeRoot, "controller", "node_modules"), {
  recursive: true,
  dereference: true,
});
await writeFile(
  path.join(runtimeRoot, "bundle.json"),
  `${JSON.stringify(
    {
      schemaVersion: 3,
      product: "socium",
      version,
      target,
      createdAt: new Date().toISOString(),
    },
    null,
    2,
  )}\n`,
  "utf8",
);

await mkdir(outputRoot, { recursive: true });
await rm(archivePath, { force: true });
const bundleEntries = ["bundle.json", "backend", "bin", "controller", "web"];
if (nativeHelperBinary) bundleEntries.push("native");
await tar.c(
  {
    cwd: runtimeRoot,
    file: archivePath,
    gzip: true,
    portable: true,
    noMtime: true,
  },
  bundleEntries,
);

const archiveChecksum = await sha256(archivePath);
await writeFile(
  path.join(outputRoot, `${archiveName}.sha256`),
  `${archiveChecksum}  ${archiveName}\n`,
  "utf8",
);
const fragment = {
  target,
  version,
  file: archiveName,
  sha256: archiveChecksum,
};
await writeFile(
  path.join(outputRoot, `socium-asset-${target}.json`),
  `${JSON.stringify(fragment, null, 2)}\n`,
  "utf8",
);
console.log(`Built ${archivePath}`);
console.log(`SHA-256 ${archiveChecksum}`);
