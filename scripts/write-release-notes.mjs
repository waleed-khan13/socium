import { readFile } from "node:fs/promises";
import path from "node:path";

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
    file: `socium-${version}-win32-x64.tar.gz`,
  },
  {
    label: "macOS",
    detail: "Apple Silicon Mac",
    file: `socium-${version}-darwin-arm64.tar.gz`,
  },
  {
    label: "Linux",
    detail: "Standard Intel or AMD PC",
    file: `socium-${version}-linux-x64.tar.gz`,
  },
];

const downloadCells = downloads
  .map(({ label, detail, file }) => `[Download for ${label}](${assetRoot}/${file})<br><sub>${detail}</sub>`)
  .join(" | ");

const output = `# Download Socium ${version}

| Windows | macOS | Linux |
|:--:|:--:|:--:|
| ${downloadCells} |

Using Windows ARM, an Intel Mac, or Linux ARM? Run the one-command installer instead; it detects the correct build automatically:

\`\`\`bash
npx -y socium@${version} onboard
\`\`\`

Downloads are verified automatically against the SHA-256 checksums stored in the release manifest. You do not need to download a separate checksum file.

## What's new

${notes}
`;

process.stdout.write(output);
