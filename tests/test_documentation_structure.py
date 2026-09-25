"""Keep living documentation navigable and aligned with the repository tree."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


LIVING_DOCS = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "architecture" / "overview.md",
    ROOT / "docs" / "architecture" / "data-dictionary.md",
    ROOT / "docs" / "architecture" / "data-model.md",
    ROOT / "docs" / "architecture" / "source-to-target.md",
    ROOT / "docs" / "data" / "ingestion.md",
    ROOT / "docs" / "data" / "source-profile.md",
    ROOT / "docs" / "data" / "validation.md",
    ROOT / "docs" / "getting-started" / "terminal-setup.md",
    ROOT / "docs" / "governance" / "decisions.md",
    ROOT / "docs" / "governance" / "ownership.md",
    ROOT / "docs" / "operations" / "deployment.md",
    ROOT / "docs" / "operations" / "job-setup.md",
    ROOT / "docs" / "operations" / "monitoring.md",
    ROOT / "docs" / "operations" / "runbook.md",
    ROOT / "docs" / "operations" / "workflow.md",
    ROOT / "docs" / "standards" / "naming.md",
]


REQUIRED_READMES = [
    ROOT / "config" / "README.md",
    ROOT / "dashboards" / "README.md",
    ROOT / "docs" / "tools" / "duckdb" / "README.md",
    ROOT / "etl" / "README.md",
    *(path / "README.md" for path in sorted((ROOT / "etl").glob("[0-9][0-9]_*"))),
    ROOT / "evidence" / "README.md",
    ROOT / "evidence" / "proof" / "README.md",
    ROOT / "evidence" / "proof" / "source-validation" / "README.md",
    ROOT / "notebooks" / "README.md",
    ROOT / "src" / "README.md",
    ROOT / "src" / "ingestion" / "README.md",
    ROOT / "tests" / "README.md",
]


STALE_CURRENT_STATE_PHRASES = {
    "The complete pipeline has not yet been orchestrated and validated end to end",
    "Status: proposed, not deployed",
    "Stages 04 to 06 are placeholder files",
    "No execution evidence exists yet",
    "Open-Meteo has no gate until it has a contract",
    "Weather and Taxi Zones gates are in progress",
}


def markdown_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and ".pytest_cache" not in path.parts
    ]


def test_required_readmes_exist_and_are_not_empty():
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_READMES if not path.is_file()]
    assert not missing, f"missing README files: {missing}"

    too_short = [
        str(path.relative_to(ROOT))
        for path in REQUIRED_READMES
        if len(path.read_text(encoding="utf-8").strip().splitlines()) < 3
    ]
    assert not too_short, f"README files need useful content: {too_short}"


def test_each_etl_readme_lists_every_sql_file_in_its_layer():
    missing_entries: list[str] = []
    for layer in sorted((ROOT / "etl").glob("[0-9][0-9]_*")):
        readme = layer / "README.md"
        text = readme.read_text(encoding="utf-8")
        for sql_file in sorted(layer.glob("*.sql")):
            if f"`{sql_file.name}`" not in text:
                missing_entries.append(str(sql_file.relative_to(ROOT)))
    assert not missing_entries, f"ETL files missing from layer README: {missing_entries}"


def test_living_documents_have_one_top_level_heading():
    failures: dict[str, int] = {}
    for path in LIVING_DOCS:
        headings = re.findall(r"^# [^#].*$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if len(headings) != 1:
            failures[str(path.relative_to(ROOT))] = len(headings)
    assert not failures, f"living documents must have exactly one H1: {failures}"


def test_markdown_local_link_targets_exist():
    broken: list[str] = []
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for raw_target in pattern.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0])
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {raw_target}")

    assert not broken, "broken local Markdown links:\n" + "\n".join(broken)


def test_known_stale_current_state_phrases_do_not_return():
    searchable = [
        ROOT / "README.md",
        ROOT / "docs" / "architecture" / "overview.md",
        ROOT / "docs" / "governance" / "ownership.md",
        ROOT / "docs" / "operations" / "job-setup.md",
        ROOT / "docs" / "data" / "validation.md",
        ROOT / "etl" / "README.md",
        ROOT / "evidence" / "README.md",
    ]
    matches: list[str] = []
    for path in searchable:
        text = path.read_text(encoding="utf-8")
        for phrase in STALE_CURRENT_STATE_PHRASES:
            if phrase in text:
                matches.append(f"{path.relative_to(ROOT)}: {phrase}")
    assert not matches, "stale current-state text returned:\n" + "\n".join(matches)


def test_documentation_index_names_every_canonical_document():
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    missing = [
        str(path.relative_to(ROOT / "docs"))
        for path in LIVING_DOCS
        if ROOT / "docs" in path.parents
        and path.name != "README.md"
        and f"({path.relative_to(ROOT / 'docs').as_posix()})" not in index
    ]
    assert not missing, f"canonical documents missing from docs/README.md: {missing}"
