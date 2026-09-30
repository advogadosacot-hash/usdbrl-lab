"""Higiene do repositório público: segurança (seção 29), P1/D2 e P9."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_GITHUB_TOKEN = re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}")
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _repo_files():
    for path in REPO.rglob("*"):
        if path.is_file() and not _SKIP_DIRS.intersection(path.relative_to(REPO).parts):
            yield path


def test_p9_no_project_license_file():
    assert not any((REPO / name).exists() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"))


def test_no_secrets_in_repository():
    offenders = []
    for path in _repo_files():
        if path.suffix in {".py", ".toml", ".yml", ".yaml", ".md", ".txt", ".json", ""}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path.name == Path(__file__).name:
                continue
            if _PRIVATE_KEY.search(text) or _GITHUB_TOKEN.search(text):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_no_market_data_files_in_public_repo():
    banned = {".parquet", ".duckdb", ".sqlite", ".db", ".csv"}
    assert [p.name for p in _repo_files() if p.suffix in banned] == []


def test_workflows_pin_actions_by_commit_sha():
    uses = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.M)
    for wf in WORKFLOWS.glob("*.yml"):
        for ref in uses.findall(wf.read_text(encoding="utf-8")):
            assert re.search(r"@[0-9a-f]{40}$", ref), f"{wf.name}: {ref} não fixado por SHA"


def test_workflows_have_no_dangerous_triggers_and_minimal_permissions():
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "pull_request_target" not in text, wf.name
        assert re.search(r"^permissions:\s*\n\s+contents:\s*read", text, re.M), wf.name


def test_ci_workflow_never_touches_secrets():
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "environment:" not in text
