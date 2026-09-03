import { readFile } from "node:fs/promises";
import path from "node:path";

import { nativeInstallerFileName } from "./native-installer-names.mjs";

const projectRoot = process.cwd();
const packageJson = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8"));
const changelog = await readFile(path.join(projectRoot, "CHANGELOG.md"), "utf8");
const version = packageJson.version;
const tag = process.env.RELEASE_TAG || `v${version}`;
const repository = process.env.GITHUB_REPOSITORY || "waleed-khan13/socium";
const serverUrl = process.env.GITHUB_SERVER_URL || "https://github.com";

if (tag !== `v${version}`) {
  throw new Error(`Release tag ${tag} does not match package version v${version}.`);
}

function changelogNotes(releaseVersion) {
  const heading = new RegExp(`^## ${releaseVersion.replaceAll(".", "\\.")} - .+$`, "m");
  const match = heading.exec(changelog);
  if (!match) return "";
  const start = match.index + match[0].length;
  const next = changelog.indexOf("\n## ", start);
  return changelog.slice(start, next === -1 ? undefined : next).trim();
}

const notes = changelogNotes(version);
if (!notes) throw new Error(`CHANGELOG.md has no release notes for ${version}.`);

const assetRoot = `${serverUrl}/${repository}/releases/download/${tag}`;
const downloads = [
  {
    label: "Windows",
    detail: "Standard Intel or AMD PC",
    file: nativeInstallerFileName(version, "win32-x64"),
  },
  {
    label: "macOS",
    detail: "Apple Silicon Mac",
    file: nativeInstallerFileName(version, "darwin-arm64"),
  },
  {
    label: "Linux",
    detail: "Standard Intel or AMD PC",
    file: nativeInstallerFileName(version, "linux-x64"),
  },
];

const downloadCells = downloads
  .map(({ label, detail, file }) => `[Download for ${label}](${assetRoot}/${file})<br><sub>${detail}</sub>`)
  .join(" | ");

const output = `# Download Socium ${version}

| Windows | macOS | Linux |
|:--:|:--:|:--:|
| ${downloadCells} |

These installers include the Socium runtime. Users do not need Node.js, Python, Rust, Docker, Git, or pnpm.

Using Windows ARM, an Intel Mac, or Linux ARM? Select the matching architecture from **Assets**, or use the command-line installer:

\`\`\`bash
npx -y socium@${version} onboard
\`\`\`

Downloads are verified automatically against the SHA-256 checksums stored in the release manifest. You do not need to download a separate checksum file.

## Code signing policy

Socium has applied to the SignPath Foundation open-source program. If accepted, signed release artifacts will use **Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org)**. An artifact is unsigned unless these release notes explicitly identify it as signed. See the [Socium code signing policy](${serverUrl}/${repository}/blob/main/docs/CODE_SIGNING_POLICY.md).

## What's new

${notes}
`;

process.stdout.write(output);
