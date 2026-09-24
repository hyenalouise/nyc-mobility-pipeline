"""databricks.yml is only the source of truth for the job if it is deployable.

It carried `resources:` alone until issue #117 — which reads like a bundle but
`databricks bundle validate` rejects before it reaches the job definition, so
changing the job by changing this file was never actually possible.

These tests hold the shape in place, and guard the three per-workspace
identifiers that were frozen into a file meant to be portable. Since #132 they
also hold the schedule, which has two easy ways to go quietly wrong, and since
#148 the source gates that must run before each Bronze loader.
"""
import copy
import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = REPO_ROOT / "databricks.yml"
JOB_NAME = "NYC_Mobility_Pipeline"


def bundle():
    return yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))


def job():
    return bundle()["resources"]["jobs"][JOB_NAME]


def schedule():
    return job().get("schedule") or {}


def strip_yaml_comments(text):
    """Drop '#' comments. databricks.yml is YAML, not SQL."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def quartz_problem(expression):
    """Why `expression` is not a usable Quartz cron, or None if it is."""
    fields = expression.split()
    if len(fields) not in (6, 7):
        return f"{len(fields)} fields; Quartz needs 6 or 7, seconds first (crontab has 5)"
    day_of_month, day_of_week = fields[3], fields[5]
    if (day_of_month == "?") == (day_of_week == "?"):
        return "exactly one of day-of-month and day-of-week must be '?'"
    return None


# --- deployability -------------------------------------------------------

def test_the_bundle_is_deployable():
    document = bundle()
    assert document.get("bundle", {}).get("name"), (
        "databricks.yml declares no bundle name, so it is a job definition rather "
        "than a bundle and cannot be deployed."
    )
    assert document.get("targets"), "databricks.yml declares no targets to deploy to."


def test_exactly_one_target_is_the_default():
    defaults = [name for name, spec in bundle()["targets"].items() if (spec or {}).get("default")]
    assert len(defaults) == 1, f"expected one default target, found {defaults}"


def test_production_targets_deploy_to_one_fixed_folder():
    """Production mode refuses to deploy without workspace.root_path, and prod
    shipped without one, so `bundle validate --target prod` failed from #117
    until #132. The path must also be the same for everyone: deployment state
    lives there, so a per-user path lets a second deploy create a duplicate
    prod job instead of updating the existing one."""
    for name, spec in bundle()["targets"].items():
        spec = spec or {}
        if spec.get("mode") != "production":
            continue
        root_path = spec.get("workspace", {}).get("root_path")
        assert root_path, f"production target {name!r} sets no workspace.root_path."
        assert "current_user" not in root_path, (
            f"production target {name!r} deploys to a per-user folder ({root_path}), "
            "so each person who deploys it gets their own copy of the prod job."
        )


def test_the_default_target_is_not_production():
    """An accidental bare `databricks bundle deploy` must not land on prod."""
    targets = bundle()["targets"]
    default = next(n for n, s in targets.items() if (s or {}).get("default"))
    assert targets[default].get("mode") != "production", (
        f"target {default!r} is both the default and production mode."
    )


# --- the identifiers that were frozen into the file ----------------------

def test_the_warehouse_is_declared_once():
    """A warehouse id is per workspace. It was written out 30 times, so the
    first deploy to a workspace whose warehouse differed needed 30 edits."""
    # [^\S\n] is "whitespace but not a newline": the declaration line in
    # `variables:` is `warehouse_id:` with nothing after it, and a pattern
    # crossing the newline would match the next key as if it were a value.
    literals = re.findall(
        r"warehouse_id:[^\S\n]*(?!\$\{)(\S+)", strip_yaml_comments(BUNDLE_PATH.read_text(encoding="utf-8"))
    )
    assert not literals, (
        f"warehouse_id is hardcoded in {len(literals)} place(s): {sorted(set(literals))}. "
        "Reference ${var.warehouse_id} so it is declared once."
    )


def test_the_warehouse_variable_exists():
    assert "warehouse_id" in bundle().get("variables", {}), (
        "tasks reference ${var.warehouse_id} but no such bundle variable is declared."
    )


def test_every_target_declares_its_workspace_host():
    """Deploying must not depend on which workspace the operator is logged in to."""
    missing = [
        name for name, spec in bundle()["targets"].items()
        if not (spec or {}).get("workspace", {}).get("host")
    ]
    assert not missing, (
        f"target(s) {missing} declare no workspace host, so a deploy lands wherever "
        "the operator is authenticated."
    )


def test_no_credentials_are_committed():
    """A host is an address. A token is not, and must never appear here."""
    leaked = re.findall(
        r"(?i)(token|password|secret|client_secret)\s*:\s*\S+",
        strip_yaml_comments(BUNDLE_PATH.read_text(encoding="utf-8")),
    )
    assert not leaked, f"credential-looking entries in databricks.yml: {leaked}"


# --- what runs must be what is recorded ----------------------------------

def test_the_source_is_pinned_to_a_commit():
    """A branch resolves at run time; ${bundle.git.commit} resolves at deploy
    time. Mixing them lets the job run one commit while recording another."""
    source = job()["git_source"]
    assert "git_branch" not in source and "git_tag" not in source, (
        "git_source is pinned to a moving ref. The job would run whatever that ref "
        "points at when it starts, not the commit that was deployed."
    )
    assert source["git_commit"] == "${bundle.git.commit}"


# --- the schedule (#132) -------------------------------------------------

def test_the_job_runs_on_a_schedule():
    """Before #132 every run was started by hand, so "how does it run
    tomorrow" had no answer and freshness had no interval to measure against."""
    assert schedule().get("quartz_cron_expression"), "the job has no schedule."


def test_the_schedule_is_quartz_not_crontab():
    """Databricks reads Quartz: seconds first, and '?' in one of the two day
    fields. A crontab line such as "0 6 * * 1" is not a Quartz expression."""
    expression = schedule()["quartz_cron_expression"]
    problem = quartz_problem(expression)
    assert problem is None, f"{expression!r}: {problem}"


def test_the_schedule_is_in_new_york_time():
    """The reporting timezone. 06:00 in any other zone is a different hour."""
    assert schedule().get("timezone_id") == "America/New_York"


def test_the_target_decides_whether_the_schedule_is_paused():
    """Development mode pauses schedules, so a dev deploy never fires on a
    timer. A pause_status on the job overrides that for every target: checked
    with `databricks bundle validate --target dev`, where an explicit UNPAUSED
    came out UNPAUSED."""
    assert "pause_status" not in schedule(), (
        "the schedule sets its own pause_status, which overrides development "
        "mode's pause: every dev sandbox would run on this timer."
    )
    for name, spec in bundle()["targets"].items():
        spec = spec or {}
        if spec.get("mode") == "development":
            assert (spec.get("presets") or {}).get("trigger_pause_status") != "UNPAUSED", (
                f"target {name!r} is development mode but unpauses its triggers."
            )


def test_the_quartz_rule_would_catch_its_regressions():
    assert quartz_problem("0 0 6 ? * MON") is None
    assert quartz_problem("0 6 * * 1") is not None      # crontab: five fields
    assert quartz_problem("0 0 6 * * MON") is not None  # both day fields set
    assert quartz_problem("0 0 6 ? * ?") is not None    # neither day field set


def test_the_rules_would_catch_their_regressions():
    pattern = r"warehouse_id:[^\S\n]*(?!\$\{)(\S+)"
    assert re.findall(pattern, "        warehouse_id: abc123\n") == ["abc123"]
    assert re.findall(pattern, "        warehouse_id: ${var.warehouse_id}\n") == []
    # The variable's own declaration is a key with no value on the line.
    assert re.findall(pattern, "  warehouse_id:\n    default: abc123\n") == []


# --- the source gates (#148) ---------------------------------------------

GATE_SCRIPT = "src/ingestion/source_gate.py"
CONTRACT_PATH = REPO_ROOT / "config" / "source_contract.json"
REQUIREMENTS_PATH = REPO_ROOT / "requirements-dev.txt"

# The Bronze loader each gated source protects. A source added to the
# contract has to be added here, or the test below fails.
LOADERS = {
    "green_taxi": "etl/02_bronze/10_load_green_taxi.sql",
    "taxi_zones": "etl/02_bronze/30_load_taxi_zones.sql",
    "weather": "etl/02_bronze/20_load_open_meteo.sql",
}


def task_running(job_definition, sql_path):
    return next(
        t for t in job_definition["tasks"]
        if (t.get("sql_task") or {}).get("file", {}).get("path") == sql_path
    )


def gate_tasks(job_definition):
    """{source: task} for every task that runs the source gate."""
    gates = {}
    for task in job_definition["tasks"]:
        python = task.get("spark_python_task") or {}
        if python.get("python_file") == GATE_SCRIPT:
            parameters = python.get("parameters", [])
            gates[parameters[parameters.index("--source") + 1]] = task
    return gates


def argument(task, flag):
    parameters = task["spark_python_task"]["parameters"]
    return parameters[parameters.index(flag) + 1]


def resolved(value):
    """A task argument as a normal run sees it: a {{job.parameters.X}}
    reference becomes X's default."""
    match = re.fullmatch(r"\{\{job\.parameters\.(\w+)\}\}", value)
    if not match:
        return value
    return next(p["default"] for p in job()["parameters"] if p["name"] == match.group(1))


def ungated_loaders(job_definition):
    """Gated sources whose Bronze loader does not wait for that source's gate."""
    gates = gate_tasks(job_definition)
    ungated = []
    for source, loader_path in LOADERS.items():
        upstream = {d["task_key"] for d in task_running(job_definition, loader_path).get("depends_on", [])}
        if source not in gates or gates[source]["task_key"] not in upstream:
            ungated.append(source)
    return ungated


def test_every_contracted_source_names_its_loader():
    contracted = set(json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))
    assert contracted <= set(LOADERS), (
        f"{sorted(contracted - set(LOADERS))} have a source contract but no Bronze loader "
        "listed here, so nothing checks that their loader waits for the gate."
    )


def test_every_bronze_loader_waits_for_its_source_gate():
    """Without the dependency a bad delivery lands in Bronze before, or
    while, the gate refuses it."""
    assert ungated_loaders(job()) == []


def test_the_gates_read_the_volume_and_record_the_deployed_revision():
    control_setup = task_running(job(), "etl/01_control/00_create_control_tables.sql")["task_key"]
    for source, task in gate_tasks(job()).items():
        assert resolved(argument(task, "--input")).startswith("/Volumes/"), (
            f"the {source} gate does not read the Volume, so it checks different files "
            "than the Bronze loader loads."
        )
        assert "--record-control" in task["spark_python_task"]["parameters"], (
            f"the {source} gate writes no rows to data_quality_results."
        )
        assert argument(task, "--code-revision") == "{{job.parameters.code_revision}}", (
            f"the {source} gate does not stamp the job's code_revision (D25)."
        )
        assert control_setup in {d["task_key"] for d in task.get("depends_on", [])}, (
            f"the {source} gate can run before data_quality_results exists."
        )


def test_the_gates_run_the_duckdb_version_ci_pins():
    """The job, CI and the committed evidence must run one engine version."""
    pinned = re.search(r"^duckdb==(\S+)", REQUIREMENTS_PATH.read_text(encoding="utf-8"), re.MULTILINE).group(1)
    environments = {e["environment_key"]: e["spec"] for e in job().get("environments", [])}
    for source, task in gate_tasks(job()).items():
        dependencies = environments[task["environment_key"]].get("dependencies", [])
        assert f"duckdb=={pinned}" in dependencies, (
            f"the {source} gate's environment has {dependencies}, but requirements-dev.txt pins duckdb=={pinned}."
        )


def test_the_dq_dashboard_waits_for_the_source_gates():
    dashboard = next(t for t in job()["tasks"] if t["task_key"] == "dq_dashboard")
    upstream = {d["task_key"] for d in dashboard["depends_on"]}
    missing = {t["task_key"] for t in gate_tasks(job()).values()} - upstream
    assert not missing, f"the DQ dashboard can refresh before {sorted(missing)} has recorded its verdict."


def loader_reads(loader_path):
    """The path a Bronze loader passes to read_files, written the way the
    gate reads it. read_files takes a folder plus a format; DuckDB needs a
    glob, so a folder becomes the folder's files of that format."""
    text = (REPO_ROOT / loader_path).read_text(encoding="utf-8")
    path = re.search(r"read_files\(\s*'([^']+)'", text).group(1)
    if path.endswith("/"):
        return path + "*." + re.search(r"format\s*=>\s*'(\w+)'", text).group(1)
    return path


def misplaced_gate_inputs(job_definition, parameters):
    """Gated sources whose gate would, by default, check something other than
    what their loader loads."""
    defaults = {p["name"]: p["default"] for p in parameters}
    misplaced = []
    for source, task in gate_tasks(job_definition).items():
        name = argument(task, "--input").removeprefix("{{job.parameters.").removesuffix("}}")
        if defaults.get(name) != loader_reads(LOADERS[source]):
            misplaced.append(source)
    return misplaced


def test_each_gate_reads_its_own_input_parameter():
    """Overriding one gate's input for a controlled test (#158) must leave
    the other gate reading its landing folder."""
    for source, task in gate_tasks(job()).items():
        assert argument(task, "--input") == f"{{{{job.parameters.{source}_input}}}}", (
            f"the {source} gate does not read the job parameter {source}_input."
        )


def test_each_gate_input_defaults_to_what_its_loader_reads():
    """A normal or scheduled run must check exactly what gets loaded. A test
    folder committed as the default would check one thing and load another."""
    assert misplaced_gate_inputs(job(), job()["parameters"]) == []


def test_the_gate_input_rule_would_catch_a_test_folder_default():
    parameters = copy.deepcopy(job()["parameters"])
    next(p for p in parameters if p["name"] == "green_taxi_input")["default"] = (
        "/Volumes/ftw-week-08/00-source/group_a_source/_test/green_taxi_blocked/*.parquet"
    )
    assert misplaced_gate_inputs(job(), parameters) == ["green_taxi"]


def test_the_gate_input_rule_would_catch_a_test_folder_inside_the_landing_folder():
    """A prefix match would accept this: it starts with the landing folder the
    loader reads, but the gate would check one file and the loader load all."""
    parameters = copy.deepcopy(job()["parameters"])
    next(p for p in parameters if p["name"] == "green_taxi_input")["default"] = (
        "/Volumes/ftw-week-08/00-source/group_a_source/green_taxi/_test/blocked.parquet"
    )
    assert misplaced_gate_inputs(job(), parameters) == ["green_taxi"]


def test_the_gate_rule_would_catch_its_regression():
    broken = copy.deepcopy(job())
    task_running(broken, LOADERS["green_taxi"])["depends_on"] = [{"task_key": "00_create_control_tables"}]
    assert ungated_loaders(broken) == ["green_taxi"]
