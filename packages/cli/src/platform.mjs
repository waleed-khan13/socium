const supportedTargets = new Set([
  "win32-x64",
  "win32-arm64",
  "darwin-x64",
  "darwin-arm64",
  "linux-x64",
  "linux-arm64",
]);

export function releaseTarget(platform = process.platform, architecture = process.arch) {
  const target = `${platform}-${architecture}`;
  if (!supportedTargets.has(target)) {
    throw new Error(
      `Socium does not have a release bundle for ${platform}/${architecture}. ` +
        `Supported targets: ${[...supportedTargets].join(", ")}.`,
    );
  }
  return target;
}

export function backendFileName(platform = process.platform) {
  return platform === "win32" ? "socium-api.exe" : "socium-api";
}

export function nativeHelperFileName(platform = process.platform) {
  return platform === "win32" ? "socium-windows-helper.exe" : null;
}

export function supportedReleaseTargets() {
  return [...supportedTargets];
}
