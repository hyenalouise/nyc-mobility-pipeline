# How we work on this pipeline

This is for everyone in the group. It doesn't assume you've used a terminal,
and it's clear about when you actually need one — which is less often than you
might think.

## Start here

| I want to… | Where | Terminal? |
|---|---|---|
| Edit a SQL gate or loader | Databricks Git folder | no |
| Run a single SQL file | Databricks Git folder | no |
| Commit and push | Databricks Git panel, or GitHub | no |
| Open or review a pull request | GitHub | no |
| Check whether the data is right | Databricks SQL editor | no |
| Run the tests before pushing | terminal | yes |
| Deploy the job | terminal | yes |

Your Databricks Git folder is a real clone of the repo, with the whole history.
Commits you make there are ordinary commits. You're not missing anything by
working in the browser.

The two things it can't do are run the test suite and deploy. That's the only
reason to learn the terminal, and it's worth it for those two alone.

---

## Part 1 — Databricks, no terminal needed

### Make your own Git folder

Create one from `https://github.com/hyenalouise/nyc-mobility-pipeline`. Don't
share a folder with someone else — you'll overwrite each other.

### Always work on a branch

Don't commit to `main`. Make a branch in the Git panel, named after the issue:

    <type>/issue-<number>-<short-description>

So `fix/issue-111-bronze-scalar-subquery`. Use `fix`, `ops`, `docs`, `deploy`
or `proof` for the type.

We lost time on 22 September because the same line got fixed two different ways
on two branches. Branch names tied to issues make that obvious early.

### Running a gate by hand

Gates read a parameter called `code_revision`. If you just hit Run, you'll get:

    [UNBOUND_SQL_PARAMETER] Found the unbound parameter: code_revision

That's not a bug. It means nothing supplied a value. Click **Add parameter**,
call it `code_revision`, and type anything — `manual-test` works. You can also
leave it empty, which records `'UNSET'`, meaning "we don't know what code
produced this".

One thing to watch: clicking Add parameter has sometimes pasted a stray
`:param_1` into the SQL itself, which then won't parse. If you see that, delete
it, and check you haven't committed it.

### Commit and push

Use the Git panel. Look at what changed, write a message, commit, push. Then
open a pull request on GitHub.

### Things that will bite you

Don't edit a file while you're running it. The editor can change the file
underneath you and the failure looks like a code problem when it isn't.

Don't commit on `main`.

Don't commit generated output. If running something changes a file you didn't
touch, that file probably shouldn't be in the repo at all.

---

## Part 2 — GitHub, no terminal needed

### Opening a pull request

The description has to contain `Closes #N`, `Part of #N` or `Related to #N`, or
a check fails it.

Say what changed and why, and what you ran to check it. Include counts if data
is involved. And say what you haven't checked — that last bit is what makes the
rest believable.

### Reading the checks

Three run on every pull request:

| Check | Fails when |
|---|---|
| Repository checks | a test fails, or a file breaks a naming or layout rule |
| Local pipeline runs | the pipeline misbehaves (added by #116) |
| PR links an issue | the description has no `Closes #N` |

Click into a failed one to see which test broke.

### Reviewing someone else's work

Read the code, not just the description. Ask rather than assume. A comment like
"this reads from the internet, but the issue says no network" is worth far more
than an approval.

You can approve, comment, or request changes. Don't approve your own.

---

## Part 3 — The terminal, for tests and deploys

Two things only. Worth learning for both.

> New to the terminal? [`docs/terminal_setup.md`](terminal_setup.md) starts from
> scratch — opening one, moving around, installing everything, and checking each
> step worked. What follows here is the summary.

### Opening one

On Mac, ⌘+Space and type Terminal. On Windows, Start and type PowerShell.
Either way, VS Code has one built in under **View → Terminal**, which opens in
whatever folder you have open.

### Commands you'll actually use

    cd <folder>        go into a folder
    ls   /  dir        list what's here (ls on Mac, dir on Windows)
    pwd                where am I
    git status         what's changed
    git log --oneline -5     last five commits

When something fails, read the message before trying again. Nearly every error
we hit told us exactly what was wrong.

### Installing

Mac:

    brew install git gh databricks

Windows:

    winget install Git.Git GitHub.cli Databricks.DatabricksCLI

Then check each one:

    git --version
    gh --version
    databricks --version

### Clone the repo

Separate from your Databricks Git folder. Both are clones; this one lets you
run tests and deploy.

    git clone https://github.com/hyenalouise/nyc-mobility-pipeline.git
    cd nyc-mobility-pipeline

### Run the tests

    pip install -r requirements-dev.txt
    python -m pytest tests -q

Four seconds, no credentials, nothing touched in Databricks. Same tests CI runs,
so running them first means fewer red pull requests.

### Log in to Databricks

    databricks auth login --host https://dbc-cd77c839-62eb.cloud.databricks.com --profile crystal-workspace

Always pass `--profile`. Without it the CLI picks whichever workspace you used
last. That's how a deploy ended up in a personal workspace on 22 September, and
the error it gave pointed at a missing warehouse rather than the real cause.

---

## Part 4 — Deploying and running

One person has the CLI set up at the moment. That's a single point of failure
and more of us should be able to do this.

### Deploy

    git switch main
    git pull --ff-only
    databricks bundle deploy --target dev --profile crystal-workspace

Your working tree has to be clean. The deploy stamps whatever commit you have
checked out onto the job, so deploying from a half-edited folder records a
commit that doesn't describe what you deployed.

Here's what the deploy does:

1. Replaces `${bundle.git.commit}` with your actual commit, in both the job's
   Git source and the `code_revision` parameter, so they can't drift apart
2. Replaces `${var.warehouse_id}` with the warehouse from `databricks.yml`
3. Uploads the bundle to your own workspace folder
4. Creates or updates the job, named `[dev <your-name>] NYC Mobility Pipeline`,
   with any schedule paused

It doesn't run anything. It only updates the definition.

### Check what landed

    databricks jobs get 224133189973974 --profile crystal-workspace

A job shows the commit it was last *deployed* from, not what's on your branch.
If the commit or parameter looks stale, you probably haven't deployed yet. This
one caught us out for an hour on 22 September.

### Run it

    databricks bundle run NYC_Mobility_Pipeline --target dev --profile crystal-workspace

Or press Run now in the Jobs UI. Tasks run in dependency order, and a failed
gate skips everything downstream rather than letting it run on data nobody
validated.

---

## Part 5 — Checking it worked

All three queries run in the Databricks SQL editor. No terminal.

**Did every gate pass?**

    SELECT layer, dataset, status, code_revision, checks_run
    FROM `ftw-week-08`.`01-control`.gate_status
    ORDER BY layer, dataset;

Fifteen rows, all PASS, and one `code_revision` across all of them.

**Do the numbers add up?**

    SELECT 'bronze  green_taxi_raw' AS table_name, COUNT(*) AS rows FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
    UNION ALL
    SELECT 'silver  green_taxi_clean',        COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_clean
    UNION ALL
    SELECT 'silver  green_taxi_quarantine',   COUNT(*) FROM `ftw-week-08`.`03-silver`.green_taxi_quarantine
    UNION ALL
    SELECT 'gold    fact_taxi_trip',          COUNT(*) FROM `ftw-week-08`.`05-gold`.fact_taxi_trip;

133,353 clean plus 14 quarantined is 133,367 in Bronze. Every row accounted for.

**Which code produced which run?**

    SELECT code_revision, COUNT(*) AS runs, MAX(started_at) AS last_seen
    FROM `ftw-week-08`.`01-control`.pipeline_runs
    GROUP BY code_revision ORDER BY MAX(started_at) DESC;

`code_revision` tells you the deployed version, not a single execution, so
several runs will share one. `run_id` is what tells executions apart.

---

## Part 6 — Using VS Code

Optional, but handy if you want the editor, the tests and a terminal in one
place.

Install VS Code, then **File → Open Folder** and pick the folder you cloned.
Install the Databricks extension from the Extensions panel and connect it using
the profile you set up above. **View → Terminal** gives you a terminal already
in the right place.

Editing here and pushing works the same as the Databricks Git folder — same
repo, same branches. Use whichever you prefer. The difference is that VS Code
can also run the tests.

---

## Part 7 — Words you'll come across

| Term | What it means |
|---|---|
| branch | a separate line of work, so two people don't overwrite each other |
| pull request | "please look at my branch and merge it" |
| CI | checks GitHub runs on every pull request |
| bundle | `databricks.yml`, the file that defines the job |
| target | where a deploy goes. `dev` prefixes the job name and pauses schedules; `prod` doesn't |
| job parameter | a value the job hands to every task, like `code_revision` |
| gate | a validation step that stops the pipeline when the data isn't acceptable |
| `${bundle.git.commit}` | gets replaced with the real commit when you deploy |
| profile | a saved Databricks login. Always name it |
| idempotent | running it twice gives the same result as running it once |

---

## Stuck?

Read the error first. Most of ours said exactly what was wrong.

Then tell someone where you are, what you ran, and what it said. "It doesn't
work" takes three messages to sort out; the error text usually takes none.
