# frontseat-cli (last updated: 2026-11-14)

`frontseat-cli` is a thin command-line client over the [`/api/v1`
endpoints](api.md). It files tasks into a project's **Planning** column and
lists existing ones, from a terminal or from a Claude Code session. It
cannot start, move, edit or delete tasks; that happens on the board, by a
human.

It is one self-contained Python 3 file (3.9 or newer, standard library only)
in [`cli/frontseat-cli`](../cli/frontseat-cli). Decision record:
[ADR-0018](adr/0018-single-file-python-cli.md).

API access is a licensed feature: without a license that includes
`api_access`, every command fails with exit code 4.

## Installation

Copy the file onto your `PATH`. That is the whole installation.

```bash
install -m 755 cli/frontseat-cli ~/.local/bin/frontseat-cli
frontseat-cli --version
```

`python3` must be on the `PATH`; the one that ships with the macOS
command-line developer tools (3.9) and every mainstream Linux distribution
works.

## Configuration

You need three things: the instance URL, a personal access token, and the
project to work in. Create the token in FrontSeat under **Account → API
tokens**.

| Setting | Sources, first match wins |
|---|---|
| Instance URL | `FRONTSEAT_URL` → `"url"` in `.frontseat` → `"url"` in the user config |
| Token | `FRONTSEAT_TOKEN` → `"token"` in the user config |
| Project | `--project ID` → `FRONTSEAT_PROJECT` → `"project"` in `.frontseat` |

**User config.** `$XDG_CONFIG_HOME/frontseat/config.json`, by default
`~/.config/frontseat/config.json`:

```json
{"url": "https://frontseat.example.com", "token": "fs_pat_…"}
```

Keep it private (`chmod 600`). The CLI warns on stderr whenever it reads a
token from a config file that other users can read.

**`.frontseat`.** A JSON file at the root of a repository (the CLI searches
from the current directory upward) naming the project the repository's tasks
belong to, and optionally the instance URL:

```json
{"project": 12, "url": "https://frontseat.example.com"}
```

It is meant to be committed, so **it must never hold a token**: a `token`
key, or any value starting with `fs_pat_`, is an error (exit 2), never a
fallback. Projects are identified by their numeric id; `frontseat-cli project
list` shows the ids.

**TLS.** The CLI uses Python's default certificate verification and has no
option to turn it off. For an instance behind a private CA, point
`SSL_CERT_FILE` (or `SSL_CERT_DIR`) at the CA bundle. Plain `http://` URLs
work as they are. Redirects are not followed, because that would resend the
token to another address. If the URL redirects (typically `http://` to
`https://`), the CLI says where to and exits with 2.

## Commands

Every command takes `--json`, which prints the API's response body unchanged,
and `--help`, which explains purpose, arguments, configuration and exit codes
with an example. That help is the main discovery surface for agents.

### `whoami`

Checks the configuration: instance URL, user, instance role, and where each
setting came from. The token itself is never printed.

```console
$ frontseat-cli whoami
URL:      https://frontseat.example.com  (from FRONTSEAT_URL)
User:     ada  (id 3, member)
Token:    from /home/ada/.config/frontseat/config.json
Project:  12  (from /home/ada/src/app/.frontseat)
```

### `project list`

```console
$ frontseat-cli project list
12     app
13     website
```

### `task list [--state planning|running|review|done] [--project ID]`

A project's tasks, newest first, without archived or cancelled ones, at most
100.

```console
$ frontseat-cli task list --state planning
#43     planning  Add CSV export
#41     planning  Debounce the search box
```

### `task create --title T [--description D | --description-file PATH|-] [--work-type W] [--project ID]`

Creates a task in Planning, attributed to you, and its timeline records the
token's name. `--description-file -` reads stdin, and file contents are used
byte for byte, so multi-line Markdown arrives intact. `--work-type` is
`code` (default), `design`, `content` or `file`.

```console
$ frontseat-cli task create --title "Add CSV export" --description-file - <<'EOF'
## Context
Users export the archive by hand today.
## Done when
- The archive page offers a CSV download
EOF
Created task #43: Add CSV export
https://frontseat.example.com/projects/12/tasks/43
```

The request is **never retried**. A retry after a timeout could create the
task twice, so on a timeout the CLI tells you to check `task list` first.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Other API error: invalid input (422, field errors listed), instance not set up, server error, unexpected response |
| 2 | Usage or configuration: bad arguments, missing URL/token/project, invalid or token-bearing `.frontseat`, a redirecting URL |
| 3 | Authentication failed (401): unknown, revoked or expired token |
| 4 | `license_required` (403): the instance's license does not include API access |
| 5 | Not found (404): the project does not exist or you are not a member |
| 6 | Could not reach the instance: connection refused, DNS, TLS or timeout. The message names the exact URL that was tried and the reason in plain words |

Errors go to stderr as `frontseat-cli: error: <message>`, where the message is
the API's own, unchanged. Field errors follow, then a `hint:` line saying what
to do next. Nothing is ever written to stdout on failure.

## The Claude skill

[`cli/skills/frontseat-tasks/`](../cli/skills/frontseat-tasks) teaches Claude
Code to use the CLI. It checks the setup with `whoami`, resolves the project
(asking when there is no `.frontseat`), lists tasks to avoid duplicates, and
creates only the items you approved, one task each, with a description that
stands on its own. It then reports every URL. It contains no URL, token or
project. Install it per project or for your user:

```bash
mkdir -p .claude/skills && cp -R /path/to/frontseat/cli/skills/frontseat-tasks .claude/skills/
# or: cp -R /path/to/frontseat/cli/skills/frontseat-tasks ~/.claude/skills/
```

Then, in a session: *"create a FrontSeat task for each of these three
improvements"*.

## Development

The tests use only the standard library and run against a stub HTTP server:

```bash
python3 -m unittest discover -s cli/tests
```

CI runs them in a separate `cli` job on Python 3.9 and 3.12. They are not
part of `mix precommit`, so working on the Elixir app needs no Python.
