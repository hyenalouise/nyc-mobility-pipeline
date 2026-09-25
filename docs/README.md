# Documentation guide

Use this page as the entry point for project documentation. Each subject has one
canonical document; other files should link to it instead of copying its tables
or status statements.

## Start here

| If you need to… | Read |
|---|---|
| Understand the system boundary and stages | [Architecture](architecture/overview.md) |
| Understand facts, dimensions, grains, and relationships | [Data model](architecture/data-model.md) |
| Look up fields, types, and measure definitions | [Data dictionary](architecture/data-dictionary.md) |
| Look up catalog, schema, table, file, and column naming rules | [Naming conventions](standards/naming.md) |
| Trace a source field to its target | [Source-to-target mapping](architecture/source-to-target.md) |
| Understand what was observed in the source data | [Source profile](data/source-profile.md) |
| Understand discovery, batch identity, loading, and reruns | [Ingestion](data/ingestion.md) |
| Understand gates, severities, and required proof | [Validation](data/validation.md) |
| Inspect the configured Databricks job graph | [Job setup](operations/job-setup.md) |
| Make, review, deploy, and verify a change | [Workflow](operations/workflow.md) |
| Deploy through GitHub Actions | [Deployment](operations/deployment.md) |
| Monitor execution and data quality | [Monitoring](operations/monitoring.md) |
| Operate a run or respond to a failure | [Runbook](operations/runbook.md) |
| Set up a terminal and Databricks CLI | [Terminal setup](getting-started/terminal-setup.md) |
| Understand ownership, access, and governance | [Governance](governance/ownership.md) |
| Understand why a design choice was accepted | [Decision log](governance/decisions.md) |
| Understand the DuckDB source gate and reconciliation | [DuckDB documentation](tools/duckdb/README.md) |

## Source-of-truth boundaries

| Topic | Executable or canonical authority | Documentation role |
|---|---|---|
| Job tasks and dependencies | [`databricks.yml`](../databricks.yml) | `operations/job-setup.md` explains the graph |
| Source acceptance rules | [`config/source_contract.json`](../config/source_contract.json) and `source_gate.py` | `tools/duckdb/` explains behavior |
| Table implementation | [`etl/`](../etl/) | architecture and model explain intent |
| Field definitions | `architecture/data-dictionary.md` | mapping explains derivation |
| Gate behavior | validation SQL and `source_gate.py` | `data/validation.md` defines the shared contract |
| Deployment workflow | [`.github/workflows/cd-deploy.yml`](../.github/workflows/cd-deploy.yml) | `operations/deployment.md` explains setup and approval |
| Monitoring thresholds and response | Control and DQ tables plus dashboard definitions | `operations/monitoring.md` explains what to watch |
| Current run results | [`evidence/pipeline-runs/`](../evidence/pipeline-runs/) | run summaries cite run and code revisions |
| Source-gate result files | [`evidence/source-validation/`](../evidence/source-validation/) | compact JSON results record accepted and controlled failing inputs |
| Design history | `governance/decisions.md` | entries preserve the context at decision time |
| Deployed workspace state | Databricks job and run metadata | repository docs must not assume a commit is deployed |

When prose disagrees with executable configuration, stop and resolve the
discrepancy. Do not silently choose whichever version is more convenient.

## Document types

### Current contracts

Architecture, model, dictionary, mapping, ingestion, validation, job setup,
workflow, deployment, monitoring, runbook, and governance describe how the
current system is expected to work. Update them in the same pull request as the
behavior they describe.

### Historical records

The decision log and committed evidence preserve what was decided or observed at
a point in time. Do not rewrite an old result to resemble the current pipeline.
Add a superseding decision or a new evidence file instead.

### Learning material

`getting-started/terminal-setup.md` and explanatory portions of
`operations/workflow.md` are written for
career shifters. They may explain terminology, but they must still link to the
same operational commands and configuration used by the team.

## Maintenance rules

- Keep the root README short enough to act as a landing page.
- Put a fact in one canonical document and link to it elsewhere.
- Do not use a future issue or an old proof result as a statement of current
  implementation status.
- Describe repository state and deployed workspace state separately.
- Include a code revision and run ID in execution claims.
- Keep proof immutable: add a new file rather than overwriting an older result.
- Update layer READMEs whenever files are added, removed, or change status.
- Run the local Markdown-link and repository-policy checks before review.

## Folder layout

Documentation is grouped by reader need:

```text
docs/
├── architecture/     system design, model, dictionary, and mapping
├── data/             source observations, ingestion, and validation
├── getting-started/  beginner environment setup
├── governance/       ownership and decision history
├── operations/       job setup, delivery, monitoring, and runbook
├── standards/        naming rules
└── tools/            tool-specific guidance such as DuckDB
```

Move documents only when their ownership changes, and update all repository
references in the same change.
