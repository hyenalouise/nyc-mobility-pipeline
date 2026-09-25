# Configuration

This folder contains non-secret project contracts and naming values.

| File | Purpose | Main consumers |
|---|---|---|
| `project.json` | Project-level platform and reporting settings | Documentation and policy tests |
| `sources.json` | Approved source registry and locations | Ingestion documentation and review |
| `source_contract.json` | Required columns, hourly fields, row floors, and reporting windows | `src/ingestion/source_gate.py` and source-gate tests |
| `naming.yml` | Approved naming rules | Repository-policy tests and contributors |

Configuration committed here must be non-secret, reviewable, and portable
between development and production targets. Workspace IDs, credentials, and
user-specific paths do not belong here.

When a contract changes, update its tests, implementation, canonical
documentation, and decision record when the business rule itself changed.
