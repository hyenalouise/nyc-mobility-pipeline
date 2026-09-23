# Terminal and Databricks CLI, from zero

For anyone in the group who hasn't used a terminal before. It's the setup one person currently does, written down so more than one of us can.

Go in order. Every step ends with a way to check it worked, so you're never moving on unsure.

## Why bother

Everything else you can do in a browser. Two things you can't:

- Running the tests before you push, so you find problems in four seconds instead of waiting for CI
- Deploying, which is how a change actually reaches Databricks

Right now one person can deploy. If that person's asleep, nothing ships.

---

## Part 1 — Opening a terminal

### Mac

⌘+Space, type `Terminal`, Enter. A window opens with a line ending in `%` or `$`. That's the prompt, waiting for you.

### Windows

Start, type `PowerShell`, Enter. The prompt ends in `>`.

### Either

If you use VS Code: **View → Terminal**. It opens inside whatever folder you have open, which is usually what you want.

### Your first command

Type this, press Enter:

    pwd

It prints where you are — something like `/Users/yourname` or `C:\Users\yourname`. That's your home folder.

The terminal is always "in" a folder, and most confusion comes from being in the wrong one. When something says "file not found", check `pwd` first.

---

## Part 2 — Five commands that cover most of it

| Command | What it does |
|---|---|
| `pwd` | print where I am |
| `ls` (Mac) / `dir` (Windows) | list what's here |
| `cd foldername` | go into a folder |
| `cd ..` | go up one level |
| `cd ~` | go home |

### Try it

    cd ~
    ls
    cd Desktop
    pwd

You should end up somewhere ending in `/Desktop`. If a folder name has a space in it, wrap it in quotes: `cd "NYC DOT Files"`.

Type the first few letters of a folder and press Tab — it completes the name and saves you typos.

---

## Part 3 — Installing the tools

Three of them: `git`, `gh` (GitHub) and `databricks`.

### Mac

You need Homebrew first, which is a program that installs other programs. See if you already have it:

    brew --version

If that says "command not found", grab the install command from [brew.sh](https://brew.sh) and follow the prompts. Takes a few minutes and it will ask for your password.

Then:

    brew install git gh databricks

### Windows

PowerShell has `winget` built in:

    winget install Git.Git
    winget install GitHub.cli
    winget install Databricks.DatabricksCLI

> Nobody in the group has run these on Windows yet. If a package name is wrong, please fix this file rather than working around it.

### Check all three

Close the terminal and open a new one first — newly installed programs only show up in a fresh terminal. Then:

    git --version
    gh --version
    databricks --version

Three version numbers and you're done. "Command not found" means that one didn't install; re-run just that one.

---

## Part 4 — Logging in to GitHub

    gh auth login

It asks a few questions. Answer GitHub.com, HTTPS, yes to authenticate git, and login with a web browser. It gives you a code to paste into the page it opens.

### Check

    gh auth status

Should say you're logged in as your username.

---

## Part 5 — Getting the code

This is separate from your Databricks Git folder. Both are real clones; this one is the one you can test and deploy from.

    cd ~/Desktop
    git clone https://github.com/hyenalouise/nyc-mobility-pipeline.git
    cd nyc-mobility-pipeline

`git clone` copies the entire history, every commit by everyone, not just the current files. The files you see are git rebuilding the newest commit for you to look at.

### Check

    git log --oneline -5

Five recent commits with their messages.

### Look around

    ls

You should see `etl/`, `docs/`, `tests/`, `databricks.yml`, `README.md`.

---

## Part 6 — Running the tests

    pip install -r requirements-dev.txt
    python -m pytest tests -q

About four seconds. No credentials, no network, nothing touched in Databricks.

You want a line like `245 passed, 1 skipped`.

These are the same tests CI runs on your pull request, so running them first means fewer red pull requests and less waiting around.

If `pip` or `python` isn't found, try `pip3` and `python3`.

---

## Part 7 — Logging in to Databricks

Read this part slowly. It's where the mistakes are quiet.

    databricks auth login --host https://dbc-cd77c839-62eb.cloud.databricks.com --profile crystal-workspace

A browser opens, you log in, and it saves a profile called `crystal-workspace`.

### What a profile is

A saved login for one workspace. You can have several, one per workspace, each with a name.

Always pass `--profile`. Without it the CLI uses whichever profile is marked default, which may be a completely different workspace.

That's not hypothetical. On 22 September a deploy ran without `--profile`, went to a personal workspace instead of the shared one, and failed with:

    Error: cannot create job: SQL warehouse 7d6db0d013d454fc does not exist

The warehouse was fine. It just existed in the *other* workspace. The error pointed nowhere near the actual cause, which was the missing flag.

### Check

    databricks auth profiles

Lists every profile, its host, and whether it still works.

    databricks warehouses list --profile crystal-workspace

Should show `Serverless Starter Warehouse`. If you're seeing a different warehouse than your teammates, you're pointed at the wrong workspace.

### Name your profiles

Someone once hit Enter at the profile-name prompt with a command still sitting in the buffer, and ended up with a profile called `databricks warehouses list`. It works. It's confusing forever. Pass `--profile <name>` yourself.

---

## Part 8 — Deploying

Only do this when you mean to. It changes a job in a shared workspace.

### 8.1 Start clean and current

    git switch main
    git pull --ff-only
    git status

`git status` has to say "nothing to commit, working tree clean".

The deploy stamps your current commit onto the job. Deploy from a half-edited folder and you pin a commit that doesn't describe what you deployed, which makes the recorded history a lie.

### 8.2 Look before you change anything

    databricks bundle validate --target dev --profile crystal-workspace

Read the output — the workspace host, your user, the path. Confirm the host is the one you expect before going further. It ends with `Validation OK!` and changes nothing.

If it says:

    Error: Unable to locate the bundle root: databricks.yml not found

you're in the wrong folder. `cd` into the repository and try again.

### 8.3 Deploy

    databricks bundle deploy --target dev --profile crystal-workspace

What happens:

1. `${bundle.git.commit}` is replaced with your current commit, in both the job's Git source and the `code_revision` parameter, so they can't disagree
2. `${var.warehouse_id}` is replaced with the warehouse from `databricks.yml`
3. Files upload to your own workspace folder
4. The job is created or updated, named `[dev <your-name>] NYC Mobility Pipeline`, with schedules paused

A deploy doesn't run anything. It only updates the definition.

### 8.4 Confirm what landed

    databricks jobs get 224133189973974 --profile crystal-workspace

Look for `git_commit` and the `code_revision` parameter. Both should be your current commit.

A job shows the commit it was last *deployed* from, not what's on your branch. If it looks stale, you haven't deployed. That one cost us an hour on 22 September and it's the most common thing to get wrong here.

### 8.5 Run

    databricks bundle run NYC_Mobility_Pipeline --target dev --profile crystal-workspace

Or press Run now in the Jobs UI. Either's fine. Takes about five and a half minutes.

---

## Part 9 — Looking at what happened

    databricks jobs list-runs --job-id 224133189973974 --limit 3 --profile crystal-workspace

Then check the data in the Databricks SQL editor. `docs/workflow.md` Part 5 has the three queries worth running.

---

## Part 10 — Errors you'll probably meet

| Message | What it means |
|---|---|
| `command not found` | not installed, or you need a fresh terminal |
| `No such file or directory` | wrong folder — run `pwd` |
| `Unable to locate the bundle root` | `cd` into the repository first |
| `multiple profiles matched` | two profiles share a host — pass `--profile` |
| `SQL warehouse ... does not exist` | usually the wrong workspace, not a missing warehouse |
| `UNBOUND_SQL_PARAMETER` | a SQL parameter wasn't given a value |
| `Your branch is behind` | run `git pull --ff-only` |

Read the message before retrying. Nearly every error we hit over two days said exactly what was wrong. The ones that cost us time were the ones where the message was accurate and we assumed it meant something else.

---

## A short checklist

Once, at setup:

- [ ] `git --version`, `gh --version`, `databricks --version` all print something
- [ ] `gh auth status` shows you logged in
- [ ] repository cloned and `git log` works
- [ ] `python -m pytest tests -q` passes
- [ ] `databricks auth profiles` lists `crystal-workspace`
- [ ] `databricks bundle validate --target dev --profile crystal-workspace` says OK

Six for six and you can deploy, and we stop depending on one person for it.
