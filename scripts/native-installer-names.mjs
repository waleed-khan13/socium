export const nativeInstallerTargets = [
  "win32-x64",
  "win32-arm64",
  "darwin-x64",
  "darwin-arm64",
  "linux-x64",
  "linux-arm64",
];

export function nativeInstallerFileName(version, target) {
  const names = {
    "win32-x64": `Socium-Setup-${version}.exe`,
    "win32-arm64": `Socium-Setup-${version}-arm64.exe`,
    "darwin-x64": `Socium-${version}-intel.dmg`,
    "darwin-arm64": `Socium-${version}.dmg`,
    "linux-x64": `Socium-${version}.AppImage`,
    "linux-arm64": `Socium-${version}-arm64.AppImage`,
  };
  const result = names[target];
  if (!result) throw new Error(`Unsupported native installer target: ${target}`);
  return result;
}
