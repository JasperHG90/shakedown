---
name: release
description: Release a new version of a project. Handles version bumping (alpha / release candidate / stable), tagging, pushing, creating a GitHub release with curated release notes, and monitoring the CI pipeline until success. Use whenever the user says "release", "new version", "tag a release", "bump version", "ship it", "cut a release", "cut an RC", "promote RC", or anything about creating a new project version/tag. NOT for releasing a Claude Code plugin that is versioned in its .claude-plugin/plugin.json and distributed straight over git with no tag-triggered build — use the `release-claude-code-plugin` skill for that.
---

# Release

Automates the full release cycle for a project, including release-candidate promotion.

## Context

This skill assumes a tag-driven release flow: pushing a `v*` tag triggers a CI workflow that builds the project's artifacts and creates a GitHub release. Before starting, confirm the project's specifics:

- **Tag convention** — read existing tags (`git tag --sort=-v:refname | head -20`) to learn the prefix (`v` vs none) and version scheme. The examples below use PEP 440 (`a`, `rc{N}`); adapt to SemVer (`-alpha.1`, `-rc.1`) or whatever the project already uses.
- **Release workflow** — find the workflow that fires on tag push (look in `.github/workflows/` for an `on: push: tags:` trigger). Note its filename for the monitoring step.
- **Repo slug** — derive `owner/repo` from `gh repo view --json nameWithOwner -q .nameWithOwner` (or `git remote get-url origin`). Use it for changelog/compare URLs instead of hardcoding.
- **What gets built** — the workflow defines this (wheels/sdists, binaries, container images, etc.). You don't need to build anything manually; the tag push does it.

Three release tracks (PEP 440 form — adapt to the project's scheme):

| Track | Tag form | Pre-release on GitHub? | When to use |
|---|---|---|---|
| Alpha | `v{M}.{m}.{p}a` (or `a1`, `a2`...) | Yes | Iterating on a feature; expect breakage |
| Release candidate | `v{M}.{m}.{p}rc{N}` (e.g. `v0.1.0rc1`) | Yes | Feature-frozen; soak/validation before final |
| Stable | `v{M}.{m}.{p}` | No (latest) | Promoted from a green RC |

- **Promotion never re-bumps**: when an RC has soaked successfully, "promote to stable" ships the same `M.m.p` minus the `rcN` suffix — no new patch number.

## Release Steps

### Step 1: Determine the new version

Read the latest tag:
```bash
git tag --sort=-v:refname | head -1
```

Parse it. Default behaviour depends on what the latest tag *is*:

- Latest is an **alpha** (`v0.0.41a`) → ask: alpha bump (`v0.0.42a`), cut RC (`v0.1.0rc1`), or stable bump (`v0.0.42`)?
- Latest is an **RC** (`v0.1.0rc1`) → ask: next RC (`v0.1.0rc2`) or **promote to stable** (`v0.1.0`)?
- Latest is **stable** (`v0.1.0`) → ask: alpha (`v0.1.1a`), RC (`v0.1.1rc1`), or stable patch (`v0.1.1`)?

Always confirm with the user before proceeding. If they want a different bump type (minor, major), accommodate that.

Version examples:

| Latest | Action | New version |
|---|---|---|
| `v0.0.41a` | alpha patch | `v0.0.42a` |
| `v0.0.41a` | start RC for next minor | `v0.1.0rc1` |
| `v0.0.41a` | stable patch | `v0.0.42` |
| `v0.1.0rc1` | next RC | `v0.1.0rc2` |
| `v0.1.0rc3` | **promote to stable** | `v0.1.0` |
| `v0.1.0` | next alpha | `v0.1.1a` |
| `v0.1.0` | start RC | `v0.1.1rc1` |
| `v0.1.0` | stable patch | `v0.1.1` |

**Promotion rule**: when promoting `v{M}.{m}.{p}rcN` to stable, the new tag is exactly `v{M}.{m}.{p}` — do not bump the patch. Promotion ships the same code as the last RC.

### Step 2: Check git log for release notes

Generate release notes from commits since the last tag:
```bash
git log $(git tag --sort=-v:refname | head -1)..HEAD --oneline
```

For an **RC promotion** (`rcN` → stable), use the range from the last *non-RC* tag (or initial commit) so the stable release notes cover the full RC cycle:
```bash
LAST_STABLE=$(git tag --sort=-v:refname | grep -v 'rc\|a$' | head -1)
git log "${LAST_STABLE}..HEAD" --oneline
```

Format each conventional commit as a bullet point:
```
- **feat(cli)**: add batch operations and move templates to common (abc1234)
- **fix(api)**: mock lifespan in tests to avoid 120s timeout (def5678)
```

For RC tags after `rc1`, the release notes should highlight what changed *since the previous RC* (the soak-fixes that justified another RC). Generate the diff from the prior RC, not from the last stable.

Show the draft release notes to the user for confirmation before proceeding.

### Step 3: Create and push the tag

Confirm with the user, then:
```bash
git tag {new_version}
git push origin {default_branch}
git push origin {new_version}
```

**Important**: Push the default branch first (so the tag points to pushed commits), then push the tag.

For RC promotion, no new commits should land between the last green RC and the stable tag — verify `git rev-parse {last_rc} == git rev-parse HEAD`. If they differ, the user is shipping different code than what was soaked; warn and confirm.

### Step 4: Monitor the release pipeline

The tag push triggers the release workflow. Monitor it (substitute the workflow filename you found in Context):
```bash
gh run list --workflow={release_workflow} --limit 1
```

Then watch the specific run:
```bash
gh run watch {run_id}
```

If the run fails, show the logs:
```bash
gh run view {run_id} --log-failed
```

### Step 5: Update the GitHub release

If CI creates the release with auto-generated notes, update it with the curated release notes and set the pre-release flag correctly. (If CI does not create a release, create it with `gh release create {new_version}` using the same flags.)

For **alpha** and **release candidate** releases (both pre-release). The `--latest=false` flag is critical — without it, the RC will be marked as the latest release on GitHub:
```bash
gh release edit {new_version} --prerelease --latest=false --notes "$(cat <<'EOF'
## What's Changed

{formatted release notes from Step 2}

**Full Changelog**: https://github.com/{owner}/{repo}/compare/{previous_version}...{new_version}
EOF
)"
```

For **stable** releases (including promoted RCs):
```bash
gh release edit {new_version} --latest --notes "$(cat <<'EOF'
## What's Changed

{formatted release notes from Step 2}

**Full Changelog**: https://github.com/{owner}/{repo}/compare/{previous_stable_version}...{new_version}
EOF
)"
```

For an RC promotion, the changelog comparison should be against the **last stable** (e.g. `v0.0.41` → `v0.1.0`), not against the last RC, so users see everything that landed in this minor bump.

### Step 6: Confirm

Print a summary:
- Previous version: `{previous_version}`
- New version: `{new_version}`
- Release type: alpha / rc / stable / **promoted** (when RC → stable)
- Release URL: `https://github.com/{owner}/{repo}/releases/tag/{new_version}`
- Pipeline status: success / failed

## Important Notes

- Never create a tag on uncommitted changes — verify `git status` is clean first.
- The release workflow builds all artifacts from the tagged commit — no manual builds needed.
- Alpha and RC releases are marked as pre-release on GitHub; stable releases (including promoted RCs) are marked as latest.
- If the workflow maintains a moving `latest` tag, the release of a stable version updates it; pre-releases should not.
- If the pipeline fails, do NOT delete the tag — investigate and fix the issue first.
- **RC promotion is code-frozen**: the stable tag must point at the same commit as the last RC. If the user wants to ship a fix on top, cut another RC (`rcN+1`) instead of bypassing the soak.
- A failed RC (soak found a bug) does not get a stable counterpart — fix forward to the next RC, not back to the broken one.
