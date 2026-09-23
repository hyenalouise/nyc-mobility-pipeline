# How we work on this pipeline

For everyone in the group. It assumes no terminal experience and says clearly
when a terminal is needed, which is less often than you might think.

## The short version

| I want to… | Where | Terminal? |
|---|---|---|
| Edit a SQL gate or loader | Databricks Git folder | no |
| Run a single SQL file | Databricks Git folder | no |
| Commit and push | Databricks Git panel, or GitHub web | no |
| Open or review a pull request | GitHub web | no |
| Check whether the data is correct | Databricks SQL editor | no |
| Run the tests before pushing | terminal | **yes** |
| Deploy the job | terminal | **yes** |

A Databricks Git folder **is** a real clone of the repository, with the whole
history. Committing from it produces ordinary commits. Nothing is lost by
working there.

The two things it cannot do are run the test suite and deploy the bundle. That
is the only reason to learn the terminal, and it is worth learning for those
two things alone.

---

## Part 1 — Working in Databricks, no terminal

### 1.1 One Git folder per person

Create your own Git folder from
`https://github.com/hyenalouise/nyc-mobility-pipeline`. Do not share one.

### 1.2 Always work on a branch

Never commit to `main`. In the Git panel, create a branch named for the issue
you are working on:

    <type>/issue-<number>-<short-description>

For example `fix/issue-111-bronze-scalar-subquery`. `<type>` is `fix`, `ops`,
`docs`, `deploy` or `proof`.

Two people fixing the same line on `main` is how we lost time on 22 September.

### 1.3 Running a gate by hand

Gates read a parameter called `code_revision`. Running one in the editor
without it fails with:

    [UNBOUND_SQL_PARAMETER] Found the unbound parameter: code_revision

That is not a bug. It means no value was supplied. Click **Add parameter**,
name it `code_revision`, and put anything in it — `manual-test` is fine. An
empty value is also fine and records `'UNSET'`, which honestly means "we do not
know what code produced this".

**Watch for one thing.** Clicking *Add parameter* has been seen to insert a
stray `:param_1` into the SQL text itself, which then fails to parse. If that
happens, delete it — and make sure you do not commit it.

### 1.4 Commit and push

Use the Git panel: review the changed files, write a message, commit, push.
Then open a pull request on GitHub.

### 1.5 What not to do

- Do not edit a file while you are running it. The editor can change the file
  under you and the failure looks like a code problem.
- Do not commit on `main`.
- Do not commit generated output. If running something changes a file you did
  not edit, that file probably should not be in the repository.

---

## Part 2 — Working in GitHub, no terminal

### 2.1 Open a pull request

Every pull request body **must** contain `Closes #N`, `Part of #N` or
`Related to #N`. A CI check fails the pull request without it.

Say what changed, why, and what you ran or checked. If data is affected,
include counts. Name anything you have not validated — that section is what
makes the rest of a pull request trustworthy.

### 2.2 Read the checks

Three run on every pull request:

| Check | Fails when |
|---|---|
| Repository checks | a test fails, or a file breaks a naming or layout rule |
| Local pipeline runs | the pipeline misbehaves — added by #116 |
| PR links an issue | the body has no `Closes #N` |

Click a failed check to see which test failed and why.

### 2.3 Review someone else's work

Read the code, not just the description. Ask questions rather than assuming
intent. A review that says "this reads from the internet, but the issue asks
for no network" is worth more than an approval.

Approve, comment, or request changes. Do not approve your own.

---

## Part 3 — The terminal, for tests and deploys

Only needed for two things. Worth learning for both.

> **Never used a terminal?** [`docs/terminal_setup.md`](terminal_setup.md) walks
> through it from zero — opening one, moving between folders, installing the
> tools, and checking each step worked. This section is the summary; that is the
> lesson.

### 3.1 Opening a terminal

- **Mac:** Terminal, or the terminal built into VS Code
- **Windows:** PowerShell, or Git Bash, or the terminal built into VS Code

In VS Code: **View → Terminal**. It opens in whatever folder you have open,
which is usually what you want.

### 3.2 The five commands that cover most of it

    cd <folder>     move into a folder
    ls   /  dir     list what is here  (ls on Mac, dir on Windows PowerShell)
    pwd             print where you are
    git status      what has changed
    git log --oneline -5    the last five commits

If a command fails, read the message before retrying. Most of ours have said
exactly what was wrong: a missing parameter, a file not found, a wrong folder.

### 3.3 Installing the tools

**Mac:**

    brew install git gh databricks

**Windows:**

    winget install Git.Git GitHub.cli Databricks.DatabricksCLI

Then check each one:

    git --version
    gh --version
    databricks --version

### 3.4 Clone the repository locally

This is separate from your Databricks Git folder. Both are clones; this one
lets you run tests and deploy.

    git clone https://github.com/hyenalouise/nyc-mobility-pipeline.git
    cd nyc-mobility-pipeline

### 3.5 Run the tests

    pip install -r requirements-dev.txt
    python -m pytest tests -q

About four seconds, no credentials, no network. These are the same tests CI
runs, so running them first means fewer red pull requests.

### 3.6 Log in to Databricks

    databricks auth login --host https://dbc-cd77c839-62eb.cloud.databricks.com --profile crystal-workspace

**Always pass `--profile`.** Without it the CLI uses whichever workspace you
last logged into. On 22 September that sent a deploy at a personal workspace
instead of the shared one, and the error it produced pointed at the wrong cause
entirely.

---

## Part 4 — Deploying and running

Today only one person has the CLI set up. That is a single point of failure,
and more of us should be able to do this.

### 4.1 Deploy

    git switch main
    git pull --ff-only
    databricks bundle deploy --target dev --profile crystal-workspace

The working tree must be clean. `${bundle.git.commit}` resolves to whatever
commit is checked out, so deploying from a half-edited folder pins a commit
that does not describe what was deployed.

What the deploy does:

1. Resolves `${bundle.git.commit}` to the real commit — into both the job's Git
   source **and** the `code_revision` parameter, so the two cannot disagree.
2. Resolves `${var.warehouse_id}` to the warehouse declared once in the file.
3. Uploads the bundle to your workspace folder.
4. Creates or updates the job. In `dev` the job is named
   `[dev <your-name>] NYC Mobility Pipeline` and any schedule is paused, so a
   deploy cannot disturb someone else's work.

A deploy updates the job. **It does not run anything.**

### 4.2 Check what landed

    databricks jobs get 224133189973974 --profile crystal-workspace

A job shows the commit it was last **deployed** from, not what is on your
branch. If the parameter or commit looks stale, you have not deployed yet.
That specific confusion cost an hour on 22 September.

### 4.3 Run

    databricks bundle run NYC_Mobility_Pipeline --target dev --profile crystal-workspace

Or press **Run now** in the Jobs UI. Tasks execute in dependency order, and a
failed gate skips everything downstream rather than letting it run on
unvalidated data.

---

## Part 5 — Checking it worked

All three run in the Databricks SQL editor. No terminal.

**Did every gate pass?**

    SELECT layer, dataset, status, code_revision, checks_run
    FROM `ftw-week-08`.`01-control`.gate_status
    ORDER BY layer, dataset;

15 rows, all `PASS`, and **one** `code_revision` across all of them.

**Do the row counts reconcile?**

    SELECT 'bronze  green_taxi_raw' AS table_name, COUNT(*) AS rows FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
    UNION ALL
    SELECT 'silver  green_taxi_clean',        COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_clean
    UNION ALL
    SELECT 'silver  green_taxi_quarantine',   COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_quarantine
    UNION ALL
    SELECT 'gold    fact_taxi_trip',          COUNT(*) FROM `ftw-week-08`.`05-gold`.fact_taxi_trip;

133,353 clean plus 14 quarantined equals 133,367 in Bronze. Every row is
accounted for.

**Which code produced which run?**

    SELECT code_revision, COUNT(*) AS runs, MAX(started_at) AS last_seen
    FROM `ftw-week-08`.`01-control`.pipeline_runs
    GROUP BY code_revision ORDER BY MAX(started_at) DESC;

`code_revision` identifies the deployed **version**, not one execution, so
several runs share it. `run_id` tells executions apart.

---

## Part 6 — Using VS Code

Optional, and useful if you want the editor, the tests and the terminal in one
place.

1. Install VS Code.
2. Open the folder you cloned in 3.4: **File → Open Folder**.
3. Install the **Databricks** extension from the Extensions panel, and connect
   it to the workspace using the profile from 3.6.
4. **View → Terminal** gives you a terminal already in the right folder.

Editing here and pushing works exactly like the Databricks Git folder — same
repository, same branches. Use whichever you prefer. The difference is that VS
Code can also run the tests.

---

## Part 7 — Words you will meet

| Term | Meaning |
|---|---|
| **branch** | a separate line of work, so two people do not overwrite each other |
| **pull request** | "please review and merge my branch" |
| **CI** | checks GitHub runs automatically on every pull request |
| **bundle** | `databricks.yml` — the file that defines the job |
| **target** | where a deploy goes. `dev` prefixes the job name and pauses schedules; `prod` does not |
| **job parameter** | a value the job passes to every task, like `code_revision` |
| **gate** | a validation step that stops the pipeline when the data is unacceptable |
| **`${bundle.git.commit}`** | replaced at deploy time with the real commit |
| **profile** | a saved Databricks login. Always name it explicitly |
| **idempotent** | running it twice gives the same result as running it once |

---

## If you are stuck

Read the error message first — most of ours named the problem exactly.

Then say where you are stuck, what you ran, and what it said. "It does not
work" takes three messages to unpick; the error text usually takes none.
