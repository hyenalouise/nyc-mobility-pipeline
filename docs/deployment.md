# Deploying from GitHub Actions

This covers the `CD Deploy` workflow (`.github/workflows/cd-deploy.yml`),
added for issue #133. It replaces running `databricks bundle deploy` from a
personal machine -- which left no shared record of who deployed what, and
had already sent a deploy to the wrong workspace once when the wrong CLI
profile was active -- with a dispatched, reviewed, logged GitHub Actions run.

## One-time setup (repo admin)

The workflow references two GitHub Environments, `dev` and `prod`, by name.
**These do not exist until someone creates them**, and if a workflow
references an environment that doesn't exist yet, GitHub silently
auto-creates it with no protection rules and no secrets the first time that
reference runs. An approval gate that was never actually configured is worse
than no gate, because it looks like protection without being any -- so this
step isn't optional.

For each of `dev` and `prod`, in **Settings -> Environments**:

1. Click **New environment**, name it exactly `dev` or `prod` (the workflow
   matches on this name).
2. Under **Deployment protection rules**, add **Required reviewers** and
   pick at least one person. This is what actually blocks the job until
   someone approves it -- without this, the environment exists but gates
   nothing.
3. For `prod` only, under **Deployment branches and tags**, choose
   **Selected branches and tags** and add `main`. The workflow also refuses
   a prod run dispatched from any other branch, but this rule means GitHub
   won't even release the prod secrets to one.
4. Under **Environment secrets**, add:
   - `DATABRICKS_HOST` -- the workspace URL (e.g.
     `https://dbc-cd77c839-62eb.cloud.databricks.com`, matching the `host:`
     already set for that target in `databricks.yml`).
   - `DATABRICKS_TOKEN` -- a **service principal** token, not a personal
     access token. A personal token ties every deploy to one person's
     Databricks account and breaks (or has to be rotated) the moment that
     person's access changes; a service principal is the team's, not an
     individual's, and can be scoped to only what the deploy job needs.

Repeat for both environments. `prod`'s required reviewer should generally be
someone other than whoever tends to dispatch prod deploys, so the approval
step means something.

## Running the workflow

**Actions -> CD Deploy -> Run workflow**, then:

- **Use workflow from**: the branch to test and deploy. The run checks out
  that branch's latest commit, re-runs the test suite on it, and deploys
  exactly that commit (`${bundle.git.commit}` in `databricks.yml` resolves
  to it). `prod` only accepts `main`.
- **target**: `dev` or `prod`.
- **deploy**: leave unchecked to validate only (the default). Check it to
  actually deploy after validating.
- **confirm**: only checked when deploying to `prod` -- type `prod` exactly.
  This is a second, independent check on top of the environment's required
  reviewer, so a fast "meant to pick dev, picked prod" mistake gets caught
  even if the reviewer approving the run is the same person who dispatched
  it.

Every run, including a validate-only one, waits for the environment's
required reviewer to approve it, because `databricks bundle validate` itself
calls the live workspace API and therefore needs the same
`DATABRICKS_HOST` / `DATABRICKS_TOKEN` secrets a real deploy does -- those
secrets aren't visible to the job until the environment is approved. What
`deploy=false` (the default) buys you is that once approved, only `validate`
runs; the `deploy` step itself is skipped, so nothing in the workspace
actually changes.

If either secret is missing on the environment, the job fails fast with a
named error (`DATABRICKS_HOST is not set...` / `DATABRICKS_TOKEN is not
set...`) pointing at exactly which environment to add it to, rather than
failing deep inside a Databricks CLI error.

## What this does not cover

This workflow deploys the bundle (`databricks bundle deploy`), which
updates the job definition. It does not run the pipeline -- that's a
separate action (`databricks bundle run`, or the Jobs UI), same as it was
before this issue. See `docs/workflow.md` Part 4 for running a deployed job
and checking what landed.

## Prerequisite note (issue #117)

Issue #133 lists issue #117 ("make databricks.yml an actual deployable
bundle") as a blocker. As of this workflow, `databricks.yml` already has a
`bundle:` name, `dev`/`prod` targets with per-target `workspace.host`, a
parameterized `warehouse_id` variable, and a `git_source` pinned to
`${bundle.git.commit}` -- all of #117's acceptance criteria -- merged via
PR #128. #117 itself is still showing as open on the issue tracker; worth
closing it out (or confirming with whoever owns it) rather than treating
#133 as still blocked.
