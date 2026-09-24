"""docs/job_setup.md's Tasks table must describe the job databricks.yml defines.

The table was written before the bundle existed and named every task with a
descriptive label (`control_setup`, `gate_source_green_taxi`, ...) instead of
its task key (`00_create_control_tables`, `05_source_gate_green_taxi`, ...).
All 30 names were wrong, so nothing in the table could be found in the
Databricks UI. These tests hold the table to the real task keys, dependencies
and files, so the next change to the job has to update the doc too.
"""
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_SETUP = REPO_ROOT / "docs" / "job_setup.md"
BUNDLE_PATH = REPO_ROOT / "databricks.yml"


def job_tasks():
    """Every non-dashboard task: key -> (dependencies, file). Dashboards have
    their own table in the doc."""
    tasks = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))["resources"]["jobs"]["NYC_Mobility_Pipeline"]["tasks"]
    result = {}
    for task in tasks:
        if "dashboard_task" in task:
            continue
        if "sql_task" in task:
            file = task["sql_task"]["file"]["path"]
        else:
            file = task["spark_python_task"]["python_file"]
        deps = sorted(d["task_key"] for d in task.get("depends_on", []))
        result[task["task_key"]] = (deps, file)
    return result


def doc_rows(text):
    """Rows of the table under '## Tasks': key -> (dependencies, file)."""
    section = text.split("\n## Tasks\n", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        key = cells[0].strip("`")
        file = re.findall(r"`([^`\s]+)", cells[2])[0]
        deps = sorted(re.findall(r"`([^`]+)`", cells[3]))
        rows[key] = (deps, file)
    return rows


def dashboard_tasks():
    """Every dashboard task: key -> dependencies."""
    tasks = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))["resources"]["jobs"]["NYC_Mobility_Pipeline"]["tasks"]
    return {
        task["task_key"]: sorted(d["task_key"] for d in task.get("depends_on", []))
        for task in tasks
        if "dashboard_task" in task
    }


def dashboard_rows(text):
    """Rows of the table under '## Dashboards': key -> task keys named in
    'Depends on'. A row that describes its dependencies in words names none."""
    section = text.split("\n## Dashboards\n", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0].strip("`")] = sorted(re.findall(r"`([^`]+)`", cells[3]))
    return rows


def gate_tasks():
    """The keys of every validation and source-gate task."""
    return sorted(key for key in job_tasks() if key.startswith(("05_source_gate_", "90_validate_")))


def test_the_table_lists_every_task_by_its_real_key():
    doc, job = doc_rows(JOB_SETUP.read_text(encoding="utf-8")), job_tasks()
    unknown = sorted(set(doc) - set(job))
    missing = sorted(set(job) - set(doc))
    assert not unknown, f"docs/job_setup.md names tasks that are not in databricks.yml: {unknown}"
    assert not missing, f"databricks.yml has tasks the Tasks table does not list: {missing}"


def test_each_row_has_the_real_dependencies_and_file():
    doc, job = doc_rows(JOB_SETUP.read_text(encoding="utf-8")), job_tasks()
    wrong = [
        f"{key}: doc says {doc[key]}, databricks.yml says {job[key]}"
        for key in sorted(set(doc) & set(job))
        if doc[key] != job[key]
    ]
    assert not wrong, "Tasks table rows disagree with databricks.yml:\n" + "\n".join(wrong)


def test_the_rules_would_catch_their_regressions():
    """The old table's first row, and a row with the right key but a wrong
    dependency, both parse into something the checks above reject."""
    old = "\n## Tasks\n\n| Task key | Type | File | Depends on |\n|---|---|---|---|\n| `control_setup` | SQL file | `etl/01_control/00_create_control_tables.sql` | — |\n"
    assert doc_rows(old) == {"control_setup": ([], "etl/01_control/00_create_control_tables.sql")}
    assert "control_setup" not in job_tasks()
    drifted = "\n## Tasks\n\n| `10_load_green_taxi` | SQL file | `etl/02_bronze/10_load_green_taxi.sql` | `00_create_control_tables` |\n"
    assert doc_rows(drifted)["10_load_green_taxi"] != job_tasks()["10_load_green_taxi"]


def test_the_dashboards_table_names_real_tasks_and_dependencies():
    """The Tasks test skips dashboard tasks, which is how `gate_analytics`
    survived in this table. A row that names its dependencies must name the
    real ones; dq_dashboard's 'every validation gate task' must stay true."""
    doc, job = dashboard_rows(JOB_SETUP.read_text(encoding="utf-8")), dashboard_tasks()
    assert sorted(doc) == sorted(job), f"Dashboards table lists {sorted(doc)}, databricks.yml has {sorted(job)}"
    for key, named in doc.items():
        documented = named or gate_tasks()
        assert job[key] == documented, f"{key}: databricks.yml depends on {job[key]}, the doc says {documented}"


def test_the_dashboards_rule_would_catch_the_old_label():
    old = "\n## Dashboards\n\n| `nyc_mobility_analytics` | NYC Mobility Analytics Dashboard | `x.lvdash.json` | `gate_analytics` |\n"
    assert dashboard_rows(old)["nyc_mobility_analytics"] != dashboard_tasks()["nyc_mobility_analytics"]
