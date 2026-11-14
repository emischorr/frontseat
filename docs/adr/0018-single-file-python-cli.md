# ADR-0018: The CLI is a single-file Python script outside the Elixir app, with a skill as the agent interface

Date: 2026-11-14
Status: accepted

## Context

ADR-0017 gave FrontSeat a small `/api/v1` for filing tasks. The first client
is a Claude Code session: the user says "create a FrontSeat task for each of
these" and expects tasks on the board. That needs a command the agent can
run from a shell, plus instructions that make the agent use it well: check
for duplicates, create only what was approved, and write descriptions that
stand on their own. The command runs on developer machines (macOS and Linux)
that have no Erlang, no FrontSeat checkout, and no package manager setup we
can rely on.

## Decision

- **One executable Python 3 file, standard library only**:
  `cli/frontseat-cli`, at least Python 3.9, the floor set by macOS's
  command-line developer tools. Copying it onto the `PATH` is the whole
  installation.
- **It lives in the repository but outside the Elixir app** (`cli/`, kept
  out of the Docker image by `.dockerignore`). It is versioned with the API
  it speaks, and is neither built nor served by the instance.
- **One command per endpoint, nothing more**: `whoami`, `project list`,
  `task list`, `task create`. `--json` passes the API body through
  unchanged.
- **Configuration from the environment, a private user file, and a
  committable `.frontseat`** (project id, optionally URL) that refuses to
  hold a token.
- **Distinct exit codes** for configuration, authentication, license, not
  found and connection failures. `task create` is never retried, and
  redirects are never followed so the token is not resent elsewhere.
- **A Claude skill is the agent interface** (`cli/skills/frontseat-tasks/`).
  The CLI stays mechanical, and the judgment about duplicates, approval,
  self-contained descriptions and no secrets lives in the skill, which
  users copy into their skills folder.
- **Tests run in their own CI job**, outside `mix precommit`, so Elixir
  contributors need no Python.

## Rejected alternatives

- **An Elixir escript.** It needs Erlang/OTP installed on every client
  machine, which is a large prerequisite just to file a task.
- **A compiled binary (Go, Rust, Burrito).** It needs a build pipeline and
  per-platform artifacts, plus a release channel, and the install becomes a
  download rather than a copy. That is out of proportion for four commands.
- **A shell script with `curl` and `jq`.** `jq` is not universally
  installed, and quoting multi-line Markdown safely is fragile. Distinct exit
  codes and clear errors are awkward to get right in shell.
- **An MCP server first.** It works only in MCP-capable clients and needs
  per-client setup and a long-running process. A CLI serves agents and humans
  alike, and an MCP adapter can sit on the same API later.
- **Batch creation from a file.** It invites filing many tasks without
  per-item approval, which the human-owns-every-decision principle argues
  against. One `create` per approved item keeps the agent honest, and every
  result is reported.

## Consequences

- Installing and upgrading means copying a file; there is no update channel.
  Packaging is a later iteration.
- Python 3.9 compatibility constrains the code (no `match`, no runtime
  `X | Y` types); CI pins 3.9 to catch regressions.
- The skill and the CLI must change together; keeping them in one folder is
  what makes that visible.
