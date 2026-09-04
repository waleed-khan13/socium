# Releasing Socium

Only a maintainer should run this procedure. A tag push publishes public GitHub Release assets and the public `socium` npm package; the manual dry-run does neither.

## One-time npm setup

Do not create or store a bypass-2FA npm token for Socium. Bootstrap the previously unpublished `socium` package interactively from a trusted maintainer computer after the matching GitHub Release assets exist:

```bash
npm login
cd packages/cli
npm publish --access public
```

Enter the current second factor only when npm prompts for it, so it is not saved in shell history. Never put it in chat, git, a local `.env`, workflow YAML, an issue, or a log. Then open the new package's settings on npmjs.com and configure trusted publishing for all later releases:

- GitHub owner: `waleed-khan13`
- Repository: `socium`
- Workflow filename: `release.yml`
- Allowed action: `npm publish`

The workflow uses Node.js 24 on a GitHub-hosted runner, grants `id-token: write`, and publishes with provenance without an npm token. After trusted publishing succeeds, restrict token-based publishing in the npm package settings.

## 1. Prepare the candidate

The worktree must be clean and every version source must agree:

```bash
pnpm install --frozen-lockfile
pnpm runtime:sync
npm audit --omit=dev --audit-level=high --prefix packaging/web-runtime
pnpm release:verify
pnpm check
```

The changelog and installation documentation must describe the same version. Do not tag a commit that has not passed CI on `main`.

## 2. Run the cross-platform dry-run

Open **Actions → Native release → Run workflow** and use:

- `ref`: `main` (or the exact candidate commit)
- `publish`: disabled

This builds Windows x64/ARM64, macOS Intel/Apple silicon, and Linux x64/ARM64 on native GitHub runners. Each job builds and health-checks the bundled FastAPI service, constructs the checksummed archive, installs it into an empty application-data root, runs `doctor`, enables disposable-profile autostart, boots and controls the installed UI/API, performs an in-place update and rollback, and proves normal uninstall preserves durable data. The dry-run uploads workflow artifacts but skips GitHub Release and npm publication.

Do not continue until all six matrix jobs are green.

## 3. Tag and publish

Create one annotated tag after the candidate commit and version are final:

```bash
git tag -a v1.3.1 -m "Socium 1.3.1"
git push origin v1.3.1
```

The tag-triggered workflow repeats all native builds rather than trusting dry-run artifacts. It then creates a three-choice Windows/macOS/Linux release page, uploads six dependency-free native installers, six architecture-specific updater archives, and `socium-manifest.json`, and publishes the CLI to npm. SHA-256 values remain inside the manifest, while sidecar files stay in internal workflow artifacts. Never move or reuse a published version tag. If publication fails after npm accepts the version, fix the issue and release a new patch version.

For the first-ever `socium` publication, the npm job is expected to remain unauthenticated until the interactive bootstrap above is completed. After the package is published and its trusted publisher is configured, re-run the failed workflow job; it will detect the existing version and finish without republishing it.

## 4. Verify the public release

Check that the workflow is green and that the GitHub Release contains six native installers, six updater archives, and one manifest beneath the three recommended download choices. Then use a clean temporary application home on a supported machine:

```bash
npx -y socium@1.3.1 onboard
npx -y socium@1.3.1 doctor
```

Also download the Windows `.exe`, macOS `.dmg`, and Linux `.AppImage` from the public release and confirm that each primary link points to the native installer rather than a runtime archive. Confirm that the browser opens on loopback, `/api/health` reports version `1.3.1` and edition `social-v1`, and normal uninstall preserves the data directory. Announce the release only after this public-download verification passes.
