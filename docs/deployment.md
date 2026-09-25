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
Repeat for both environments. `prod`'s required reviewer should generally be
someone other than whoever tends to dispatch prod deploys, so the approval
step means something.

## Before the first real deploy

A validate-only run needs nothing beyond the environment secrets. `databricks.yml` sets no `run_as`, so a deployed job runs as whoever deployed it: after the first `deploy: true` from this workflow, the job and its schedule run as the service principal (`github-actions-deploy`). Before that, a workspace admin grants it:

- **Can use** on the SQL warehouse (`bd9af8d40007e504`)
- access to the `ftw-week-08` catalog, its schemas and tables, and the source Volume, e.g. by adding it to the `ftw-week-09` group
- permission to run serverless jobs, which the source-gate tasks use
- read and write on `/Workspace/Shared/.bundle/nyc-mobility-pipeline/prod`, where the prod deployment state lives. Without it, the deploy can't see the existing state and creates a second prod job instead of updating the real one

Prove the grants with a `dev` deploy and one run as the service principal before the first `prod` deploy. In `dev`, the failure email goes to the service principal's own user name, so nobody receives it.

Its token lasts 90 days. Whoever renews it creates a new token for the service principal and replaces `DATABRICKS_TOKEN` in both environments.

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
