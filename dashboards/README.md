# Dashboards

This folder contains the dashboard definitions for the NYC Mobility Pipeline
project. Each `.lvdash.json` file is the deployable source of truth:
`databricks.yml` declares it as a bundle-owned resource
(`resources.dashboards`), and the job's dashboard tasks reference that
resource rather than a hardcoded dashboard id, so a deploy into a workspace
that has never held these dashboards creates them there (#122).

## Available Dashboards

### 1. NYC Mobility Data Quality Dashboard

Related Issue: #44
Definition file: `11_data_quality_dashboard/10_NYC_mobility_data_quality_dashboard.lvdash.json`

Purpose:
- Monitor pipeline health
- Track validation results
- Surface failed DQ checks
- Monitor freshness and reconciliation results

Key Features:
- Validation status by source and layer
- DQ failure trends
- Row count reconciliation
- Source and layer filtering
- Pipeline health monitoring

---

### 2. NYC Mobility Analytics Dashboard

Related Issue: #43
Definition file: `11_analytics_dashboard/10_NYC_mobility_analytics_dashboard.lvdash.json`

Purpose:
- Present validated answers to approved business questions
- Support mobility, weather, and taxi-zone analysis

Key Features:
- Trip activity by date and hour
- Pickup and dropoff analysis
- Weather impact analysis
- Zone-level metrics
- Business KPI visualizations

---

## Dashboard Evidence and Folder Structure

dashboards/
├── README.md
├── 11_data_quality_dashboard/
│   └── 10_NYC_mobility_data_quality_dashboard.lvdash.json
└── 11_analytics_dashboard/
    └── 10_NYC_mobility_analytics_dashboard.lvdash.json

Each `.lvdash.json` is exported directly from the workspace; it is not
edited by hand. Screenshots or other supporting evidence, if needed, go
alongside the definition file in the same folder.
