# Socium CLI

The `socium` npm package installs and runs the localhost application without Docker, Python, uv, pnpm, or a source checkout. Node.js 20.9 or newer is the only prerequisite.

```bash
npx -y socium@latest onboard
```

The onboarding command selects the release bundle for the current operating system and CPU, verifies its published SHA-256 checksum, installs the immutable runtime under the operating system's application-data directory, initializes a separate durable data directory, starts the FastAPI and Next.js processes on loopback, and opens the console.

## Commands

```bash
npx -y socium@latest onboard
npx -y socium@latest onboard --data-dir "D:\\Socium\\data" --models-dir "D:\\Socium\\models"
npx socium start
npx socium doctor
npx socium update
npx socium update check
npx socium backup create
npx socium backup list
npx socium rollback
npx socium autostart enable
npx socium storage move --data-dir "E:\\Socium\\data" --models-dir "E:\\Socium\\models"
npx socium uninstall --yes
```

`--data-dir` selects the durable location for SQLite, its WAL, `master.key`, media, logs, exports, and backups. `--models-dir` independently selects the usually much larger local-AI model location. Updates retain both choices. `onboard --autostart` enables start-after-login; `--no-shortcuts` skips native shortcuts. Updates create a checksum-backed data backup and migration health check before activation. Stop Socium before `backup restore` or `storage move`; both preserve the replaced/source directory until you confirm the result.

If a configured data drive is disconnected, Socium reports `Data drive unavailable` and does not create a blank database at a fallback path. The dashboard reports category usage, free space, and warnings for low-space, removable, network, or cloud-synced locations.

Uninstall preserves the SQLite database, encryption key, media, and exports by default. Add `--purge-data` only when that local business data should be permanently removed.

Docker Compose remains an optional deployment path and is not required by this CLI.
