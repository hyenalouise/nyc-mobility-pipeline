# Terminal and Databricks CLI, from zero

A walkthrough for anyone in the group who has not used a terminal before. It
covers the setup one person currently does, so that more than one of us can.

Work through it in order. Every step ends with a way to check it worked, so you
never move on wondering.

## Why bother

Everything else can be done in a browser. Two things cannot:

- **Running the tests** before you push, so you find problems in four seconds
  instead of waiting for CI
- **Deploying** the job, which is how a change actually reaches Databricks

Right now one person can deploy. If that person is asleep, nothing ships.

---

## Part 1 — Opening a terminal

### Mac

Press **⌘ + Space**, type `Terminal`, press Enter. A window opens with a line
ending in `%` or `$`. That is the prompt — it is waiting for you.

### Windows

Press **Start**, type `PowerShell`, press Enter. The prompt ends in `>`.

### Either

If you use VS Code: **View → Terminal**. It opens inside whatever folder you
have open, which is usually what you want.

### Your first command

Type this and press Enter:

    pwd

It prints where you currently are — something like `/Users/yourname` or
`C:\Users\yourname`. That is your home folder.

**The terminal is always "in" a folder.** Most confusion comes from being in
the wrong one. When something says "file not found", check `pwd` first.

---

## Part 2 — Five commands that cover most of it

| Command | What it does |
|---|---|
| `pwd` | print where I am |
| `ls` (Mac) / `dir` (Windows) | list what is here |
| `cd foldername` | go into a folder |
| `cd ..` | go up one level |
| `cd ~` | go home |

### Try it

    cd ~
    ls
    cd Desktop
    pwd

You should end up somewhere ending in `/Desktop`. If a folder name has a space,
wrap it in quotes: `cd "NYC DOT Files"`.

**Tip:** type the first few letters of a folder and press **Tab**. It completes
the name and avoids typos.

---

## Part 3 — Installing the tools

We need three: `git`, `gh` (GitHub) and `databricks`.

### Mac

Mac needs Homebrew first — a program that installs other programs. Check
whether you have it:

    brew --version

If that says "command not found", install it by pasting the command from
[brew.sh](https://brew.sh) and following the prompts. It takes a few minutes
and will ask for your password.

Then:

    brew install git gh databricks

### Windows

PowerShell has `winget` built in:

    winget install Git.Git
    winget install GitHub.cli
    winget install Databricks.DatabricksCLI

> Not yet run on a Windows machine by anyone in the group. If a command name is
> wrong, please correct this file rather than working around it.

### Check all three

**Close the terminal and open a new one** — new programs are only visible to a
fresh terminal. Then:

    git --version
    gh --version
    databricks --version

Three version numbers means you are done. "Command not found" means that one
did not install; re-run just that install.

---

## Part 4 — Logging in to GitHub

    gh auth login

It asks a few questions. Answer: **GitHub.com**, **HTTPS**, **yes** to
authenticate git, and **login with a web browser**. It shows a code, you paste
it into the browser page it opens.

### Check

    gh auth status

Should say you are logged in as your username.

---

## Part 5 — Getting the code

This is separate from your Databricks Git folder. Both are real clones; this
one lets you run tests and deploy.

    cd ~/Desktop
    git clone https://github.com/hyenalouise/nyc-mobility-pipeline.git
    cd nyc-mobility-pipeline

`git clone` copies the **entire history** — every commit by everyone, not just
the current files. The files you see are git rebuilding the newest commit for
you to look at.

### Check

    git log --oneline -5

Five recent commits with their messages.

### Find your way around

    ls

You should see `etl/`, `docs/`, `tests/`, `databricks.yml`, `README.md`.

---

## Part 6 — Running the tests

    pip install -r requirements-dev.txt
    python -m pytest tests -q

About four seconds. No credentials, no network, nothing touched in Databricks.

You want a line like `245 passed, 1 skipped`.

These are the same tests CI runs on your pull request, so running them first
means fewer red pull requests and less waiting.

If `pip` or `python` is not found, try `pip3` and `python3`.

---

## Part 7 — Logging in to Databricks

This is the part worth reading slowly, because it is where mistakes are quiet.

    databricks auth login --host https://dbc-cd77c839-62eb.cloud.databricks.com --profile crystal-workspace

A browser opens, you log in, it saves a **profile** called `crystal-workspace`.

### What a profile is

A saved login for one workspace. You can have several — one per workspace — and
each has a name.

**Always pass `--profile`.** Without it the CLI uses whichever profile is
marked default, which may be a different workspace entirely.

That is not hypothetical. On 22 September a deploy ran without `--profile`,
went to a personal workspace instead of the shared one, and failed with:

    Error: cannot create job: SQL warehouse 7d6db0d013d454fc does not exist

The warehouse was perfectly valid — in the *other* workspace. The error pointed
nowhere near the real cause, which was the missing flag.

### Check

    databricks auth profiles

Lists every profile, its host, and whether it still works.

    databricks warehouses list --profile crystal-workspace

Should show `Serverless Starter Warehouse`. If it shows a different warehouse
than your teammates see, you are pointed at the wrong workspace.

### Name profiles carefully

Someone once pressed Enter at the profile-name prompt with a command still in
the buffer, and created a profile literally called `databricks warehouses list`.
It works, but it is confusing forever. Pass `--profile <name>` yourself.

---

## Part 8 — Deploying

Only do this when you mean to. It changes a job in a shared workspace.

### 8.1 Start from a clean, current checkout

    git switch main
    git pull --ff-only
    git status

`git status` must say "nothing to commit, working tree clean".

**Why it matters:** the deploy stamps the current commit onto the job. A
half-edited folder pins a commit that does not describe what was deployed, and
the recorded history becomes a lie.

### 8.2 Check before you change anything

    databricks bundle validate --target dev --profile crystal-workspace

Read the output: the workspace host, your user, the path. **Confirm the host is
the one you expect** before going further. It ends with `Validation OK!` and
changes nothing.

If it says:

    Error: Unable to locate the bundle root: databricks.yml not found

you are in the wrong folder. `cd` into the repository and try again.

### 8.3 Deploy

    databricks bundle deploy --target dev --profile crystal-workspace

What happens:

1. `${bundle.git.commit}` is replaced with your current commit — in both the
   job's Git source and the `code_revision` parameter, so they cannot disagree
2. `${var.warehouse_id}` is replaced with the warehouse from `databricks.yml`
3. Files upload to your own workspace folder
4. The job is created or updated, named `[dev <your-name>] NYC Mobility
   Pipeline`, with schedules paused

**A deploy does not run anything.** It only updates the definition.

### 8.4 Confirm what landed

    databricks jobs get 224133189973974 --profile crystal-workspace

Look for `git_commit` and the `code_revision` parameter. **Both should be your
current commit.**

A job shows the commit it was last **deployed** from — not what is on your
branch. If it looks stale, you have not deployed. That confusion cost an hour
on 22 September, and it is the single most common thing to get wrong here.

### 8.5 Run

    databricks bundle run NYC_Mobility_Pipeline --target dev --profile crystal-workspace

Or press **Run now** in the Jobs UI. Either is fine. It takes about five and a
half minutes.

---

## Part 9 — Looking at what happened

    databricks jobs list-runs --job-id 224133189973974 --limit 3 --profile crystal-workspace

Then check the data in the Databricks SQL editor — see `docs/workflow.md`,
Part 5, for the three queries that matter.

---

## Part 10 — Errors you will probably meet

| Message | What it means |
|---|---|
| `command not found` | not installed, or you need a fresh terminal |
| `No such file or directory` | you are in the wrong folder — run `pwd` |
| `Unable to locate the bundle root` | `cd` into the repository first |
| `multiple profiles matched` | two profiles share a host — pass `--profile` |
| `SQL warehouse ... does not exist` | usually the wrong workspace, not a missing warehouse |
| `UNBOUND_SQL_PARAMETER` | a SQL parameter was not given a value |
| `Your branch is behind` | run `git pull --ff-only` |

**Read the message before retrying.** Nearly every error we hit over two days
said exactly what was wrong. The ones that cost time were the ones where the
message was accurate and we assumed it meant something else.

---

## A short checklist

Once, at setup:

- [ ] `git --version`, `gh --version`, `databricks --version` all print something
- [ ] `gh auth status` shows you logged in
- [ ] repository cloned and `git log` works
- [ ] `python -m pytest tests -q` passes
- [ ] `databricks auth profiles` lists `crystal-workspace`
- [ ] `databricks bundle validate --target dev --profile crystal-workspace` says OK

If all six pass, you can deploy — and we stop depending on one person for it.
