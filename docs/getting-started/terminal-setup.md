# Terminal and Databricks CLI setup

This guide covers prerequisites only. The change, deployment, and verification
process lives in [workflow.md](../operations/workflow.md).

## Open a terminal

- **macOS:** open Terminal with Spotlight, or use **View → Terminal** in VS Code.
- **Windows:** open PowerShell, Windows Terminal, or the VS Code terminal.

Useful commands:

| Command | Meaning |
|---|---|
| `pwd` | Show the current folder |
| `ls` | List files on macOS/Linux |
| `dir` | List files in PowerShell |
| `cd <folder>` | Enter a folder |
| `git status --short` | Show changed and untracked files |
| `git log --oneline -5` | Show the latest five commits |

Read an error before trying a second command. It often identifies the missing
tool, wrong folder, invalid profile, or permission directly.

## Required tools

The repository uses:

- Git;
- Python;
- the Databricks CLI;
- optionally GitHub CLI and VS Code.

Confirm what is already installed:

```bash
git --version
python3 --version
databricks --version
```

The examples below use `python3`, which is the command available on the team's
macOS setup. On Windows, use `py` or `python` if that is the command reported by
your installation.

Installation methods vary by operating system and may change. Use the official
installation instructions approved by the team rather than copying an old
version number from this repository.

## Get the repository

```bash
git clone https://github.com/hyenalouise/nyc-mobility-pipeline.git
cd nyc-mobility-pipeline
git status --short --branch
```

An empty status means the checkout has no local modifications. It does not mean
the local branch is current; use `git fetch` and inspect its relationship to
`origin/main` before starting work.

## Create a Python environment

Using a virtual environment keeps repository dependencies separate from other
projects:

```bash
python3 -m venv .venv
```

Activate it using the command appropriate for your shell, then install the
development dependencies:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-dev.txt
```

`.venv/` is local state and must not be committed.

## Run the local checks

```bash
python3 -m pytest tests
git diff --check
```

These commands do not connect to Databricks. They are safe for ordinary local
development and CI-equivalent validation.

## Configure Databricks authentication

Create or use the team-approved CLI profile. For the course workspace, the
repository documentation refers to the profile name:

```text
crystal-workspace
```

Confirm authentication without deploying or running anything:

```bash
databricks auth profiles
databricks current-user me --profile crystal-workspace
```

Never commit `.databrickscfg`, access tokens, client secrets, or copied profile
contents.

## Validate repository location and state

Before following workflow commands:

```bash
git rev-parse --show-toplevel
git status --short --branch
git log -1 --oneline --decorate
```

Stop if the folder is not the intended repository, the branch is not the one
you expected, or unrelated changes are present.

## Next step

Continue with [workflow.md](../operations/workflow.md) for branch, PR, bundle validation,
deployment, and verification. Use [runbook.md](../operations/runbook.md) when operating or
recovering a job.
