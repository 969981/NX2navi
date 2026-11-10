# Tracking NX2navi upstream

This repository monitors [tangerineturtle1/NX2navi](https://github.com/tangerineturtle1/NX2navi) through
[upstream-sync-release.yml](../.github/workflows/upstream-sync-release.yml).

## Schedule and permission

The workflow checks upstream twice per hour, at minutes 17 and 47 UTC. GitHub Actions cron
is best-effort and may run late. It can also be started from **Actions → Monitor NX2navi
upstream and publish → Run workflow**.

**Monitoring works without any extra configuration.** It compares upstream `main` with
the commits already contained in this repository and checks the latest *published*
upstream release against this repository's Releases. The detection result is recorded
in the workflow's run summary.

NX2navi's `LICENSE-ADDITIONS` states that its new and changed material cannot be copied
or republished without the copyright holder's **written permission**. Public read access
does not constitute redistribution permission.

Accordingly, synchronization and release mirroring are **disabled by default**.
If you have obtained the required written authorization, open:

**Repository → Settings → Secrets and variables → Actions → Variables**

Create the repository variable:

- Name: `NX2NAVI_MIRROR_AUTHORIZED`
- Value: `true`

This flag is an authorization acknowledgement, **not** a grant of rights or a substitute
for the copyright holder's permission. Leave it unset or set it to `false` without permission.

## What happens when authorized

1. When upstream `main` has commits absent from the current repository, the workflow
   merges the upstream commit into local `main`. It does **not** force push or
   reset away repository-specific files. Merge conflicts fail the job for manual
   review. Before pushing, it runs `python3 tools/check_content.py`.
2. For each successful synchronization, it creates a GitHub **pre-release**
   named `upstream-<12-character-upstream-SHA>`. This is a **source-only snapshot**,
   not a Windows build.
3. When a newer upstream **official release** is found, it downloads the official
   release attachments, checks any SHA-256 digests available from GitHub's release API,
   retains the upstream tag commit and publishes an **unofficial mirror release**
   in this repository. Only NX2navi setup, app, runtime ZIP and update manifest
   asset name patterns are accepted. It does not rebuild or re-sign binaries.
4. If neither upstream source nor its latest official release has changed, no new
   release is made. Already mirrored release tags are skipped.

All publishing runs use the repository's built-in `GITHUB_TOKEN` with
`contents: write`. No personal access token is required under ordinary repository
settings. The GitHub App/Actions policy must allow the token to write repository
contents and create releases.

The upstream installer's launcher may still update from the **official upstream
feed**. Merely mirroring release assets does not change that embedded setting.

## Failure and safety behavior

- The upstream is merged, never overwritten with `git reset --hard` or `--force`.
- A merge conflict or failure of the source content check stops that run.
- If an upstream tag in this repository points to a different commit, publication
  stops rather than moving that tag.
- Unexpected release attachment names or an available-but-incorrect SHA-256 digest
  stop publication for review. Older attachments with no API-provided digest emit
  a warning.
- Changes not yet part of a tagged upstream release produce source snapshots
  only. The official Windows installer can only be mirrored after upstream
  publishes it.
- A push performed with `GITHUB_TOKEN` does not trigger the regular `push` workflow
  again, so the content check is run explicitly before pushing.

**Do not redistribute Nintendo game data.** The workflow mirrors only upstream
repository content and published upstream artifacts; it does not build games or
include game dumps, firmware or keys.
