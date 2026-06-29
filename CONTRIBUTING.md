# Contributing to `hacode.infra`

A walk-through of how work happens in this repo, written for someone
who's about to send a PR (and maybe send their LLM with it). Not a
checklist — read the prose, lean on the reasons.

## Branches and PRs

Every change reaches `master` through a pull request. There's no
exception for trivial doc tweaks or release commits — they all go
through the same flow, because it keeps `master` linear and gives
CI a chance to catch the surprises.

A branch carries exactly one logical change. When the PR merges, it
collapses to one commit on `master` — we use rebase-merge, so the
commit message you wrote on the branch is the one that ships. Iterate
freely while the PR is open (amend, force-push, redo the description),
but think of the final state as a single, well-told story.

Branches are named after what they do, with a type prefix that lines
up with the commit message: `feat/k8s-addons-cilium`,
`fix/k3s-node-ip`, `docs/contributing`. Release branches drop the
prefix — `release-v0.2.1` — mirroring the bare `release:` commit
prefix. Once the PR is merged, the branch is gone — pull master
locally before starting the next one so history stays clean.

A few don'ts:

- Don't push to `master`. If a fix is so urgent you'd want to, it's
  more important to get a green CI on a PR than to skip the loop.
- Don't force-push to `master`. Force-pushing your own feature
  branch is fine and expected (use a lease so you don't clobber a
  push you didn't see).
- Don't skip pre-commit / pre-push hooks. They're there for a
  reason; if one's wrong, fix the hook.

**If you're using an LLM to drive the branch**, also avoid
interactive rebase — it expects a human at the editor, which the
agent can't reliably drive, and a half-finished interactive rebase
is easy to lose. When commits need reshaping, soft-reset to the
base and recommit, or use a non-interactive `--onto`.

## Commit messages

Subject lines follow Conventional Commits: `feat(scope):` for new
features, `fix(scope):` for bug fixes, `refactor(scope):` for
behaviour-preserving cleanups, `docs(scope):` for documentation,
`chore(scope):` for repo plumbing. Version bumps are the one
exception — they use a bare `release:` prefix, not `chore(release):`.

The subject is a single short sentence in the imperative. The body
covers *why*, in whatever amount of detail the change deserves —
the diff already shows *what*. Multi-paragraph bodies are welcome
when the rationale benefits from them; one-line commits are fine
when the subject already tells the whole story.

**If you're using an LLM to author or edit commits**, two extra
constraints:

- Drop the `Co-Authored-By:` trailer it adds by default. Commits
  should read as the maintainer's own work.
- Don't let it summarise what the diff already shows. Lines like
  "docs / CHANGELOG / README updated" or "added tests for …" are
  noise — the diff is the source of truth for *what*. The body
  earns its keep by explaining *why*.

## Code and comments

The bar for a comment is: would removing it confuse a future reader?
If the line under it is self-explanatory, the comment is dead weight
and should go. Restating what a task does, what a function returns,
what a variable holds — that's the kind of comment that piles up
and rots.

What's worth writing down: the reason a default is what it is, a
subtle edge case the code handles, a workaround for a bug in something
upstream, an invariant that isn't enforced by the type system. The
file that needs the most care is `roles/<name>/defaults/main.yml` —
those comments aren't internal notes, they're documentation an
operator reads when they wonder "what does this variable do." Treat
them like API docs.

Avoid commentary about who calls what or when it was added. That
context belongs in commit messages and PRs, not in code that lives
on forever.

YAML files are `.yml`, not `.yaml`. The project picked one and stuck
with it; mixing extensions makes globbing patterns and `find`
invocations annoying. Module names are fully qualified
(`ansible.builtin.copy`, not `copy`) — ansible-lint's production
profile enforces this and so should you.

## Documentation

Each role has its own README under `roles/<name>/`. Variables get
documented there in a small table; tasks get tags listed in another;
non-trivial examples live in code blocks. Keep the per-role READMEs
focused on that role — Galaxy badges, collection-wide install
instructions, project links all belong in the top-level README, never
duplicated per-role.

The `machine` role's subroles follow a pattern that's worth knowing
before you add a new one: an `_enabled` boolean toggle plus a list (or
dict) of items. If the list is empty by default and the task is a
no-op on empty input — `cron`, `disks`, `systemd_dropins` — the
toggle can default to `true`. Otherwise default it to `false` so
existing inventories don't suddenly start doing new things.

## CHANGELOG

The format is Keep-a-Changelog: one section per version with
`### Added`, `### Changed`, `### Fixed`, etc. as needed. For shipped
versions we keep entries short — one line per merged commit, with a
link to the commit so anyone can click through for the full story.
Long-form prose lives in commit messages and PR descriptions, not
in the changelog.

The `[Unreleased]` block at the top can hold longer entries while
work is in flight; when a release is cut, those collapse to the
one-line style. Breaking changes get a `**Migration**:` line under
their `### Changed` entry, calling out what an existing inventory
needs to do.

**If you're using an LLM to edit the changelog**, watch for
duplicate `### Changed` (or `### Added`) headings under the same
release section — LLMs love to add a new heading next to an
existing one. Markdownlint rejects this; merge them into one
section instead.

## PR descriptions

A good PR description has two parts: a `## Summary` that tells the
story in prose (with the occasional code block when it helps), and a
`## Test plan` that lists what you actually ran. Anything that lives
on the PR page itself doesn't need to be in the description — in
particular, **don't** add a "CI matrix green" checkbox to the test
plan. CI status is shown above the description and the checkbox will
sit unticked forever, which reads worse than not having it.

Cross-reference issues, prior PRs, or commit hashes when they
motivate the change. If there's a breaking move, name it in the
summary, not buried in the test plan.

## Lint and CI

There's a single local gate: the `lint` make target. It runs
`yamllint`, `ansible-lint` against the production profile, and
`markdownlint` against every Markdown file in the tree. Running it
before pushing catches a lot — the same checks run on CI, so a
failure locally is a failure remotely.

For role behaviour, scenarios under `extensions/molecule/` cover
each role against four platforms (two RHEL-family, two Debian-
family). You'll usually want the per-scenario target while iterating
on a specific role; the all-scenario run is too slow for a tight
loop. Running CI on every push is fine, but it's polite to make a
reasonable effort locally first.

CI itself fans out into about twenty jobs per PR: a handful of
sanity / lint passes across the supported `ansible-core` versions,
and one molecule job per scenario. Transient flakes happen —
container registry timeouts, runner deaths, a TLS handshake that
fails on retry. Those can be re-queued without changing the diff.
Real regressions get a reproduction first; *then* a fix.

## Molecule

Each role has a scenario in `extensions/molecule/<role>/` with the
standard four files: `molecule.yml` (platforms and `group_vars`),
`prepare.yml` (bare-minimum host setup the role assumes is there),
`converge.yml` (run the role), `verify.yml` (assertions about the
end state).

When you add a new subrole or feature that's exercisable inside a
docker container — and most things are — extend the matching
scenario. The bar is a small fixture in `group_vars` and one or two
`failed_when:` assertions in `verify.yml`. Where a real install is
out of scope (a Helm chart that won't run in a privileged container,
say), an offline `helm template` smoke-test against the chart's
schema is the usual fall-back.

The platform matrix is intentional. Skipping a family ("we only run
on RHEL anyway") sets up a real-world surprise the day someone
points the role at a Debian box. Stick to all four unless a
scenario has a specific reason to deviate, and document the reason
in the scenario's `molecule.yml` header when it does.

## Releases

A release is its own PR on a branch named `release-vX.Y.Z`.
It bumps the version in `galaxy.yml`, promotes everything currently
under `[Unreleased]` into a dated section in the changelog, and
ships as a single `release: vX.Y.Z` commit. The PR runs through CI
just like any other change.

After the release PR merges, the version tag is pushed against the
merged commit on `master` — tagging the branch HEAD before merge
puts the tag on a commit that no longer exists. A matching GitHub
release follows, with notes copied from the changelog section so
the project's release page lines up with what's documented.

Versioning is SemVer. Patches (the `Z` bump) carry a focused fix
on top of a `X.Y.0`. Minor bumps batch features and any
behavioural changes that aren't strictly additive. A major bump is
reserved for `1.0` — until then, breaking changes ship in a minor
with migration notes in the changelog.
