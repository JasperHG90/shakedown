# /release

A Claude Code skill that automates a tag-driven release cycle: version bumping (alpha / release candidate / stable), tagging, pushing, creating a GitHub release with curated notes, and monitoring the CI pipeline to completion. Project-agnostic — it reads the project's existing tags, release workflow, and repo slug instead of hardcoding any of them.

## What it does

1. **Determine the new version** — reads the latest tag and proposes the next one based on what the current tag is (alpha / RC / stable), then confirms with you.
2. **Draft release notes** — formats conventional commits since the last tag into bullet points for review.
3. **Tag and push** — pushes the default branch first, then the tag (which triggers CI).
4. **Monitor CI** — watches the release workflow run and surfaces logs on failure.
5. **Update the GitHub release** — sets curated notes and the correct pre-release / latest flags.
6. **Summarize** — previous version, new version, release type, URL, pipeline status.

## Release tracks

| Track | Tag form (PEP 440 example) | Pre-release? | When |
|---|---|---|---|
| Alpha | `v0.0.42a` | Yes | Iterating; expect breakage |
| Release candidate | `v0.1.0rc1` | Yes | Feature-frozen; soak before final |
| Stable | `v0.1.0` | No (latest) | Promoted from a green RC |

**Promotion never re-bumps**: promoting `v0.1.0rc3` to stable ships the exact same commit as `v0.1.0` — no new patch number.

## Assumptions

The skill auto-detects these at the start of a run; confirm them if the project differs:

- A CI workflow fires on `v*` tag pushes and builds the artifacts (`.github/workflows/` with an `on: push: tags:` trigger).
- Tag prefix and version scheme are inferred from existing tags (PEP 440 or SemVer).
- The `owner/repo` slug comes from `gh repo view` / the git remote.

## Usage

```
/release
```

Then follow the prompts. The skill confirms before every irreversible step (tag, push, release edit).

## Safety

- Refuses to tag on a dirty working tree.
- Never deletes a tag on pipeline failure — investigate and fix forward.
- RC promotion is code-frozen: the stable tag must point at the same commit as the last RC.
