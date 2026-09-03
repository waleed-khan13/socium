# Socium code signing policy

## Signing status

Socium has applied to the SignPath Foundation open-source program. If the application is accepted and signing is activated, release artifacts produced after activation will use **Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org)**. Existing artifacts remain unsigned unless their GitHub Release notes explicitly state that they are signed.

## What may be signed

Only official Socium installers built from the public [`waleed-khan13/socium`](https://github.com/waleed-khan13/socium) repository may be submitted for signing. An eligible artifact must:

- be produced by the repository's GitHub Actions release workflow from an immutable `v*` tag;
- be built entirely from the source and build definitions in that repository;
- have the Socium product name and one consistent release version in its metadata; and
- match the checksums published in that release's `socium-manifest.json`.

Locally built, modified, ad-hoc, or third-party artifacts are not eligible for the Socium signing process.

## Team roles

Socium is currently maintained by one individual:

- Committer and reviewer: [Waleed Khan (`@waleed-khan13`)](https://github.com/waleed-khan13)
- Signing approver: [Waleed Khan (`@waleed-khan13`)](https://github.com/waleed-khan13)

Changes from outside contributors must be submitted through a pull request and reviewed before merge. Every signing request requires a separate manual approval after the tagged source, workflow result, version metadata, and checksums have been reviewed. Multi-factor authentication is required for repository and signing-service access.

## Release verification

The complete build history is public in [GitHub Actions](https://github.com/waleed-khan13/socium/actions), and official artifacts are published only on [GitHub Releases](https://github.com/waleed-khan13/socium/releases). The release manifest contains the SHA-256 checksum for every installer and command-line runtime archive. A valid future signature will confirm the automated build's origin; users should still download only from the official release page and verify that the release notes identify the artifact as signed.

## Privacy and removal

Socium does not operate a hosted application backend. Local data and user-requested provider transfers are described in the [privacy notice](PRIVACY.md). Installation, normal removal that preserves local business data, and explicit permanent data removal are documented in the [installation guide](INSTALLATION.md).
