# Change and delivery workflow

This document defines the controlled path from an issue to a verified
Databricks deployment. It assumes terminal and CLI prerequisites are already
configured; beginners can start with
[terminal setup](../getting-started/terminal-setup.md).

## Delivery path

```text
Issue
  → branch
  → local checks
  → pull request
  → CI
  → teammate review
  → merge
  → deploy to dev
  → verify dev
  → approved deploy to prod
  → verify prod
  → scheduled operation
```

Repository changes, deployments, and job runs are separate events. A merge does
not deploy, and a deployment does not automatically prove that the job ran
successfully.

## 1. Start from current Main

```bash
git switch main
git pull --ff-only
git switch -c <type>/issue-<number>-<short-description>
```

Use your own local checkout or Databricks Git folder. Do not share a mutable Git
folder with another teammate.

## 2. Make and review the change locally

```bash
git status --short
git diff
python3 -m pytest tests
git diff --check
```

The local suite checks repository and source-gate contracts. It does not execute
the Databricks SQL pipeline or validate workspace permissions.

When a change affects `databricks.yml`, validate the intended targets with the
approved profile:

```bash
databricks bundle validate --target dev --profile crystal-workspace
databricks bundle validate --target prod --profile crystal-workspace
```

Bundle validation is read-only. Review its resolved target, job name, workspace
path, schedule, variables, and warnings.

## 3. Commit only intended files

```bash
git add <specific-paths>
git status --short
git commit -m "<clear description>"
git push -u origin <branch-name>
```

Do not use a broad add command without inspecting the working tree. Raw data,
credentials, local databases, generated notebook output, and large logs must not
enter the repository.

## 4. Open and review the pull request

The pull request must:

- link the tracking issue using an accepted phrase;
- explain the change and reason;
- list validation performed;
- include compact data or run evidence when applicable;
- identify remaining uncertainty;
- receive the assigned teammate's review.

CI runs repository checks, local source-gate checks, and the PR-description
contract. CI has no Databricks credentials and cannot prove live SQL execution.

## 5. Deploy to development

Deploy only an approved, clean revision:

```bash
git status --short
git rev-parse HEAD
databricks bundle deploy --target dev --profile crystal-workspace
```

The development target uses a personal workspace path and pauses the schedule.
Deployment updates resources but does not itself run the job.

Inspect the deployed job and confirm:

- the Git revision matches the intended commit;
- `code_revision` resolves to the same commit;
- source inputs and warehouse are correct;
- the schedule is paused;
- expected tasks and dashboards are present.

Do not copy a job ID from documentation. Resolve the job created by your bundle
target because personal development job IDs differ.

## 6. Run and verify development

After deployment is verified, an authorized operator may run:

```bash
databricks bundle run NYC_Mobility_Pipeline \
  --target dev \
  --profile crystal-workspace
```

Use [runbook.md](runbook.md) for success criteria, queries, and failure
response. Record the job/run ID and deployed revision before making a claim.

## 7. Promote to production

Production promotion requires the assigned production approval and a reviewed
development result. Before deployment:

1. verify the exact commit being promoted;
2. validate the production target;
3. review the shared workspace path and permissions warning;
4. verify notifications and schedule configuration;
5. confirm no test input overrides are present.

An authorized operator then deploys the same reviewed revision using the
production target. Do not rebuild or edit the change between development and
production verification.

## 8. Verify production

Confirm in Databricks:

- deployed Git revision;
- complete task and dashboard inventory;
- schedule and pause state;
- failure notifications;
- latest run result;
- gate results and reconciled data output.

Repository configuration describes intended production state. Only the
workspace proves what is currently deployed and running.

## Source-gate demonstrations

Each source gate has a job parameter for an input override. A test input that
differs from the loader's configured landing input exits with code 4 even when
its checks pass. This deliberately prevents the loader from publishing data the
gate did not inspect.

Use overrides only in an isolated development demonstration. Never place bad
test data in a production landing folder.

## Rollback and recovery

- Fix or revert through the same branch, CI, review, and deployment path.
- Preserve failed run and DQ history.
- Do not hand-edit trusted tables to imitate a successful run.
- Use a repair or rerun only after identifying whether the failure was data,
  code, configuration, permissions, or platform availability.
- Reconcile affected data again after recovery.

See [runbook.md](runbook.md) and [evidence/proof/](../../evidence/proof/).
