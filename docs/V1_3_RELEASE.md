# Socium v1.3 native installer release

Release readiness: complete for v1.3.0.

## User promise

A non-technical user can download one normal installer for their operating system, open it, and start Socium without installing Node.js, Python, Rust, Docker, Git, pnpm, or uv. The application continues to run on localhost and stores mutable business data outside its replaceable runtime.

## Release artifacts

- Windows x64: `Socium-Setup-1.3.0.exe`
- Windows ARM64: `Socium-Setup-1.3.0-arm64.exe`
- macOS Apple silicon: `Socium-1.3.0.dmg`
- macOS Intel: `Socium-1.3.0-intel.dmg`
- Linux x64: `Socium-1.3.0.AppImage`
- Linux ARM64: `Socium-1.3.0-arm64.AppImage`

The three prominent release links select Windows x64, macOS Apple silicon, and Linux x64. Alternate architectures remain visible under Assets. Runtime `.tar.gz` files remain updater inputs and advanced command-line installer assets; they are not presented as the normal direct download.

## Installation contract

- The native bootstrap embeds the platform runtime archive and its expected SHA-256 checksum.
- Extraction rejects absolute paths, parent traversal, symbolic links, and hard links.
- Bundle metadata and required executable files are validated before activation.
- The runtime is installed under the native per-user Socium application-data root without administrator access.
- Existing SQLite, encryption key, media, exports, and selected model location are preserved.
- Opening an older installer never replaces a newer active installation.
- Windows setup creates desktop and Start-menu shortcuts through the compiled native helper.
- macOS ships an application inside a DMG; Linux ships a real AppImage.
- Each platform build runs both the installed-runtime smoke test and the native-installer smoke test before upload.

## Signing boundary

The workflow produces installable artifacts with checksums. Apple notarization and trusted Windows Authenticode signing require maintainer-owned certificates and are intentionally separate release credentials. Until those credentials are configured, operating systems may show an unknown-publisher warning.
