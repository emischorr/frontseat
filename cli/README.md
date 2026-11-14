# frontseat-cli

A single-file command-line client for the FrontSeat API: file tasks into a
project's Planning column and list existing ones, from a terminal or a Claude
Code session. Python 3.9+, standard library only.

```bash
install -m 755 frontseat-cli ~/.local/bin/frontseat-cli   # any directory on your PATH
frontseat-cli --help
```

- [`frontseat-cli`](frontseat-cli): the executable, and all of the CLI.
- [`skills/frontseat-tasks/`](skills/frontseat-tasks): a Claude skill that
  teaches Claude Code to use it. Copy it into `.claude/skills/` (a project's or
  `~/.claude/skills/`).
- [`tests/`](tests): `python3 -m unittest discover -s cli/tests` from the repo root.

Configuration, commands, exit codes and the skill are covered in
[`docs/cli.md`](../docs/cli.md). API access needs a FrontSeat license that
includes it.
