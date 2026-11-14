---
name: frontseat-tasks
description: Create, file or list tasks and projects on a FrontSeat board with the frontseat-cli command. Use when the user asks to create, file, add or log FrontSeat tasks (e.g. "create a FrontSeat task for each of these", "put this on the FrontSeat board"), to see which tasks a FrontSeat project already has, or to list their FrontSeat projects.
allowed-tools: Bash(frontseat-cli whoami *), Bash(frontseat-cli project list *), Bash(frontseat-cli task list *), Bash(frontseat-cli task create *)
---

# FrontSeat tasks

`frontseat-cli` files tasks into a FrontSeat project's **Planning** column and
lists existing ones. It cannot start, move, edit or delete tasks; a human does
that on the board. Never try to, and never promise that work will start.

Run `frontseat-cli <command> --help` for any detail not covered here.

## 1. Check the setup

```bash
frontseat-cli whoami
```

On exit 2 (configuration), 3 (authentication) or 4 (license), show the user
the error and hint **exactly as printed** and stop. Do not try to fix tokens or
URLs yourself, and never ask the user to paste a token into the chat.
If the command is not found, tell the user to install `frontseat-cli` (see
`docs/cli.md` in the FrontSeat repository) and stop.

## 2. Know the project

`whoami` prints the project and where it came from (`--project`,
`FRONTSEAT_PROJECT`, or a `.frontseat` file in the repository). If it says
`Project:  not set`:

1. Run `frontseat-cli project list`.
2. Ask the user which project to use.
3. Pass `--project ID` to every later command, and offer to write
   `{"project": ID}` to `.frontseat` at the repository root (it is safe to
   commit and must never contain a token).

## 3. Check for duplicates

```bash
frontseat-cli task list --json
```

Compare each proposed item with the existing titles and descriptions. Skip
clear duplicates and mention any that look close, so the user can decide.

## 4. Create only what was approved

- If the user approved a specific set of items, create exactly those, no more.
- If the request is vague ("file the good ideas"), show the proposed titles
  first and wait for a yes.

Create **one task per item**. Pass the description through stdin so Markdown
survives intact:

```bash
frontseat-cli task create --title "Short imperative title" --description-file - <<'EOF'
## Context
Why this matters and what prompted it.

## Change
What to change, and why this approach.

## Relevant files
- path/to/file.ex: what is there

## Done when
- An observable check that tells it is finished
EOF
```

The person or agent who picks the task up **will not have this conversation**.
Each description must stand on its own: name files, functions and behaviour
explicitly, without "as discussed" or "the issue above". Add
`--work-type design|content|file` when the work is not code.

Never put secrets, tokens, passwords or private keys in a title or
description.

## 5. Report

List every created task with the id and the URL the CLI printed, plus anything
skipped as a duplicate.

If a create fails with exit 6 (timeout or connection) or an unexpected exit 1,
the task **may already exist**. Run `frontseat-cli task list` before retrying,
and never retry blindly. On exit 1 with field errors, fix the input and
try again. On exit 5, the project is wrong or inaccessible: go back to step 2.
