# Contributing

This guide covers how the team changes the NYC Mobility pipeline. Technical
contracts live in `docs/`; this file does not duplicate their complete tables or
rules.

## Before starting

1. Confirm the GitHub issue, scope, owner, and reviewer.
2. Check prerequisites and related decisions.
3. Start from current `main` in your own Git checkout or Databricks Git folder.
4. Use a development target and personal workspace path for testing.
5. Keep one branch focused on one issue or one tightly related change.

Current ownership and approval responsibilities are maintained in
[docs/governance/ownership.md](docs/governance/ownership.md).

## Branch names

Use:

```text
<type>/issue-<number>-<short-description>
```

Examples:

```text
docs/issue-162-organize-documentation
quality/issue-153-source-gate-parity
ops/issue-126-dq-owners
```

## Make the smallest coherent change

- Do not mix a path-only reorganization with pipeline-logic changes.
- Do not copy transformation logic into notebooks or a second implementation.
- Update the canonical document when behavior or a contract changes.
- Add a new decision when an accepted rule changes; do not silently rewrite the
  reason for an older decision.
- Add new run evidence rather than overwriting previous evidence.
- Never claim a repository commit is deployed without workspace evidence.

The canonical document map is [docs/README.md](docs/README.md).

## Naming and locations

- Persisted SQL references use fully qualified `catalog.schema.table` names.
- Catalog and schema identifiers are enclosed in backticks.
- Outside source-preserving Bronze fields, use lowercase `snake_case`.
- Keep production SQL in the numbered `etl/` folders.
- Keep exploratory work under `notebooks/`.
- Keep source-gate Python under `src/ingestion/`.
- Keep non-secret source and contract values under `config/`.
- Keep raw data, local databases, generated exports, and credentials out of Git.

Full naming rules are in
[docs/standards/naming.md](docs/standards/naming.md).

## Pipeline safety rules

- A source advances only when its own source, Bronze, and Silver gates pass.
- Integration waits for every required source's Silver gate.
- Gold waits for Integration; Analytics waits for Gold.
- Business dashboards refresh only after validated Analytics output.
- Never bypass a failed gate, manually mark it successful, or hand-edit a
  trusted table to make a run appear healthy.
- Preserve failed run, batch, and quality records for diagnosis.

See [docs/data/validation.md](docs/data/validation.md) and
[docs/operations/runbook.md](docs/operations/runbook.md).

## Local checks

Run from the repository root:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests
git diff --check
```

When the bundle changes, also validate the intended target with the approved
Databricks CLI profile. Bundle validation is read-only; deployment and job runs
are separate, authorized actions.

## Review your change

Before committing:

```bash
git status --short
git diff --check
git diff
```

Stage specific paths rather than the entire working directory:

```bash
git add <specific-paths>
git commit -m "<clear description>"
```

## Pull-request requirements

Every pull request must:

- reference the tracking issue using the repository's accepted issue-link form;
- explain what changed and why;
- state what was tested;
- identify affected data contracts, tables, jobs, or dashboards;
- include compact evidence when data or runtime behavior changed;
- state what remains unverified;
- receive the assigned review before merge.

The pull-request template and CI checks enforce the repository-specific details.

## Evidence requirements

For a data-affecting change, record the applicable items:

- source version, checksum, request window, or path;
- code revision and runtime context;
- source and target row counts;
- accepted and quarantined counts;
- uniqueness and required-field results;
- at least one meaningful measure reconciliation;
- incremental, rerun, or failure-recovery behavior when relevant;
- anything that remains unverified.

Store concise reviewed run summaries under `evidence/pipeline-runs/`. Store
compact source-gate result files under `evidence/source-validation/`. Large logs and raw
result exports belong in the approved external storage location.

## Security

Never commit:

- Databricks tokens or `.databrickscfg`;
- R2 credentials, passwords, or secret values;
- raw Parquet, CSV, or JSON source datasets;
- local DuckDB or other processing-state files;
- notebook output containing data or configuration;
- large generated evidence.

Stop and ask the team when a requested change requires broader production
permissions, a new external integration, or a governance decision.
