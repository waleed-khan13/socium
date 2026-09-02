# Installing Socium

Socium runs entirely on your computer. The first `npx` installation needs Node.js 20.9 or newer; the installed release carries its own Node runtime for shortcuts and background starts. It does not need Docker, Python, uv, pnpm, or a source checkout.

## Install and start

Run the same command in PowerShell, Terminal, or a Linux shell:

```bash
npx -y socium@latest onboard
```

Add `--autostart` to start Socium after login, or `--no-shortcuts` if desktop/Start-menu shortcuts are not wanted:

```powershell
npx -y socium@latest onboard --autostart
```

Choose separate locations during the first install when the system drive is small:

```powershell
npx -y socium@latest onboard --data-dir "D:\Socium\data" --models-dir "D:\Socium\models"
```

The data directory contains SQLite and its WAL files, `master.key`, media, logs, exports, and backups. The model directory is separate so large local-AI downloads can use another drive. Both selections are saved and preserved by future updates.

When Socium opens with a fresh database, the browser starts a guided first-run wizard. It shows the exact selected paths and drive health, guides one local or cloud AI connection, confirms the brand profile, and stores resumable progress only in local SQLite. **Set up later** closes the wizard without pretending setup is complete; reopen it from **Setup guide**. No Socium login is created.

The CLI detects the operating system and CPU, downloads the matching GitHub Release archive over HTTPS, verifies its published SHA-256 checksum, installs it, starts FastAPI and Next.js on loopback, and opens `http://127.0.0.1:3000`. The first start creates SQLite, applies migrations, and generates the local encryption key.

On Windows, desktop integration is handled by Socium's small native Rust helper. It provides the tray menu, folder selection dialog, desktop/Start-menu shortcuts, and start-after-login entry without starting PowerShell in the background. The dashboard still opens in the user's normal browser and all application services remain bound to localhost.

Supported release targets are Windows x64/ARM64, macOS Intel/Apple silicon, and Linux x64/ARM64. A release is published only after its native runner completes the installed-bundle health smoke test.

## Lifecycle commands

Start or run an existing installation. Keep the terminal open and press `Ctrl+C` to stop both local services:

```bash
npx socium start
npx socium run
```

Check the installation or print the CLI version:

```bash
npx socium doctor
npx socium version
```

Update to the latest verified runtime, or force a fresh runtime download to repair an incomplete installation:

```bash
npx socium@latest update
npx socium@latest update --force
```

`start` and `run` open the same installed runtime. `doctor` checks Node, installation metadata, native API and web files, the data directory, and default ports. **System & updates** in the dashboard performs the same safe update through the local controller. Before activation, Socium creates a backup, verifies the downloaded SHA-256, applies migrations in a temporary health check, and automatically rolls back if that check fails.

Manage start-after-login explicitly:

```bash
npx socium autostart status
npx socium autostart enable
npx socium autostart disable
```

Create, inspect, or restore durable data backups while Socium is stopped:

```bash
npx socium backup create
npx socium backup list
npx socium backup restore --file "/path/to/socium-backup-....tar.gz"
npx socium rollback
```

The dashboard can create a consistent backup while Socium is running. Offline restore preserves the replaced directory as `data.before-restore-<timestamp>` rather than deleting it. Keep the archive and its `.sha256` sidecar together.

To move one or both durable locations later, stop Socium with `Ctrl+C`, choose paths that do not already exist, and run:

```powershell
npx socium storage move --data-dir "E:\Socium\data" --models-dir "E:\Socium\models"
```

Socium copies and hashes every file before atomically activating the destinations. The old locations are deliberately preserved; start Socium, confirm the dashboard and content are correct, then remove the old copies yourself. If the configured data drive is missing, startup stops with `Data drive unavailable` instead of silently creating an empty database elsewhere.

Stop Socium with `Ctrl+C` before uninstalling. Normal uninstall removes downloaded runtimes but deliberately preserves business data:

```bash
npx socium uninstall --yes
```

Permanent deletion is explicit:

```bash
npx socium uninstall --yes --purge-data
```

That command removes installed runtimes, downloads, the SQLite database, `master.key`, media, and exports. Back up the whole `data` directory first; the database and its matching encryption key must stay together.

## Local files

| Platform | Application root |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Socium` |
| macOS | `~/Library/Application Support/Socium` |
| Linux | `$XDG_DATA_HOME/socium` or `~/.local/share/socium` |

The root contains `runtimes/<version>/<target>` for replaceable program files, `launcher` for the stable native entry, `backups` for offline/update archives, and the installation record. Durable data and local models use the paths chosen during onboarding; their defaults are `data` and `models` under the application root. Set `SOCIUM_HOME` before every CLI command only when an advanced or portable location is required.

On Windows, **Change storage locations** opens the native folder picker. Socium copies SQLite and durable assets first, verifies file sizes and SHA-256 checksums, switches the saved paths only after validation, and preserves the previous folders for manual recovery.

Open **Connections → Local storage** in the dashboard to see the runtime, data, and model paths, per-category data use, drive free space, and reliability warnings. Prefer a fixed local drive. SQLite on removable, network, or cloud-synced storage can be disconnected or synchronized at unsafe times.

## Ports and Labs

The console and internal API default to `127.0.0.1:3000` and `127.0.0.1:8000`. Both remain loopback-only. If either port is occupied:

```bash
npx socium start --port 3100 --api-port 8100
```

Ports `3000` (dashboard) and `8000` (private FastAPI service) are preferred defaults, not hard requirements. If either port is already occupied, Socium automatically selects the next available localhost port, passes the selected API address to the dashboard, and opens the browser on the selected dashboard URL. `--port` and `--api-port` set preferred starting ports and receive the same safe fallback behavior.

## LinkedIn without an API connection

After approving a LinkedIn revision, choose **Browser handoff** in the approval queue. Socium opens LinkedIn in a new tab, copies the exact approved caption and hashtags, and downloads the approved local image when one is attached. Paste the caption, attach the downloaded image, review the result, and press **Post** yourself. This mode needs no LinkedIn token and never reads the signed-in browser session; fully automatic LinkedIn publishing continues to use the official OAuth/API connector.

Lead intelligence and Local SEO remain preview workspaces in v1. Start them explicitly with `npx socium start --labs`.

## Release verification

Every GitHub Release includes the platform archive, a matching `.sha256` file, and `socium-manifest.json`. The CLI verifies the published archive checksum before extraction and validates the version/target metadata inside the archive. It refuses plain HTTP release downloads by default. The dashboard checks no more than once per day while idle and sends only the installed version, operating system, and CPU architecture needed to select a release.

Docker Compose remains available as an optional advanced deployment path. It is not used by the one-command installer.
