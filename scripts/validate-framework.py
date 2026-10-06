#!/usr/bin/env python3
"""Validate the Agentic SDLC Kit repository contract (HTML documents, CR-103)."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_html  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_METADATA = ("id", "title", "type", "domain", "module", "tags", "priority")
ALLOWED_TYPES = {"governance", "planning", "execution", "report", "intelligence", "reference"}
SKIPPED_PARTS = {".git", ".agents", ".venv", "venv", "__pycache__", "node_modules"}

REQUIRED_TEMPLATES = {
    "epic-template.html",
    "task-template.html",
    "context-package-template.html",
    "issue-template.html",
    "blocker-template.html",
    "change-request-template.html",
    "decision-template.html",
    "risk-template.html",
    "implementation-report-template.html",
    "review-report-template.html",
    "qa-report-template.html",
    "release-report-template.html",
}

REQUIRED_PROMPTS = {
    "project-bootstrap-prompt.html",
    "project-onboarding-prompt.html",
    "roadmap-lock-prompt.html",
    "epic-expansion-prompt.html",
    "executor-prompt.html",
    "reviewer-prompt.html",
    "qa-prompt.html",
    "release-manager-prompt.html",
}

PROMPT_HEADINGS = {
    "Role",
    "Responsibilities",
    "Required Inputs",
    "Allowed Actions",
    "Forbidden Actions",
    "Required Outputs",
    "Validation Rules",
}

COMMON_TEMPLATE_HEADINGS = {
    "Usage Purpose",
    "Record Metadata",
    "Related Files",
    "Completion Criteria",
    "Forbidden Actions",
    "Output Requirements",
}

ROADMAP_STATUSES = {
    "ROADMAP_DRAFT",
    "ROADMAP_APPROVED",
    "ROADMAP_ACTIVE",
    "ROADMAP_BLOCKED",
    "ROADMAP_DONE",
    "ROADMAP_CANCELLED",
}
MILESTONE_STATUSES = {"proposed", "ready", "in-progress", "blocked", "completed", "cancelled"}
EPIC_STATUSES = {
    "EPIC_PROPOSED",
    "EPIC_READY",
    "EPIC_IN_PROGRESS",
    "EPIC_BLOCKED",
    "EPIC_DONE",
    "EPIC_CANCELLED",
}
TASK_STATUSES = {"pending", "in-progress", "blocked", "review", "done", "cancelled"}
EDGE_STATUSES = {"active", "satisfied", "blocked", "removed"}
SESSION_OUTCOMES = {"in-progress", "completed", "partial", "blocked", "failed", "cancelled", "corrected"}
CONTEXT_STATUSES = {"current", "stale", "archived"}

RUNTIME_STATUSES = {
    "issues": {"open", "triaged", "in-progress", "blocked", "resolved", "closed", "rejected"},
    "blockers": {"open", "investigating", "workaround-active", "resolved", "accepted", "cancelled"},
    "change-requests": {
        "draft",
        "proposed",
        "under-review",
        "approved",
        "rejected",
        "implementing",
        "implemented",
        "withdrawn",
        "superseded",
    },
    "decisions": {"proposed", "under-review", "accepted", "rejected", "superseded", "deprecated"},
    "risks": {"identified", "analyzing", "mitigating", "monitoring", "accepted", "realized", "closed"},
    "implementation": {"draft", "complete", "blocked", "superseded"},
    "review": {"draft", "changes-required", "approved", "rejected", "superseded"},
    "qa": {"draft", "passed", "failed", "blocked", "superseded"},
    "releases": {"planned", "ready", "approved", "deploying", "deployed", "failed", "rolled-back", "cancelled", "superseded"},
}

EXPECTED_ENUM_LINES = {
    "AGENT.html": [
        "pending | in-progress | blocked | review | done | cancelled",
        "EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED",
    ],
    ".agent/templates/task-template.html": ["pending | in-progress | blocked | review | done | cancelled"],
    ".agent/templates/epic-template.html": [
        "EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED"
    ],
    ".agent/execution/task-board.html": ["pending | in-progress | blocked | review | done | cancelled"],
    ".agent/planning/epics.html": [
        "EPIC_PROPOSED | EPIC_READY | EPIC_IN_PROGRESS | EPIC_BLOCKED | EPIC_DONE | EPIC_CANCELLED"
    ],
    ".agent/planning/roadmap.html": [
        "ROADMAP_DRAFT | ROADMAP_APPROVED | ROADMAP_ACTIVE | ROADMAP_BLOCKED | ROADMAP_DONE | ROADMAP_CANCELLED"
    ],
}

COMMON_REQUIRED_PATHS = {
    "AGENT.html",
    "docs/00-project/release-notes-v1.0.0.html",
    "docs/00-project/installation.html",
    ".agent/planning/roadmap.html",
    ".agent/planning/milestones.html",
    ".agent/planning/epics.html",
    ".agent/planning/dependency-graph.html",
    ".agent/execution/current-context.html",
    ".agent/execution/task-board.html",
    ".agent/execution/sessions-history.html",
}

DISTRIBUTION_REQUIRED_PATHS = {
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "scripts/install-kit.sh",
    "scripts/install-kit.ps1",
}

OVERLAY_REQUIRED_PATHS = {
    "AGENTIC-SDLC-KIT.html",
    "LICENSE.agentic-sdlc-kit",
}

OVERLAY_DOCUMENTS = {
    "AGENT.html",
    "AGENTIC-SDLC-KIT.html",
    "docs/00-project/index.html",
    "docs/00-project/installation.html",
    "docs/00-project/release-notes-v1.0.0.html",
    "docs/01-business/index.html",
    "docs/01-business/srs.html",
    "docs/02-architecture/architecture.html",
    "docs/02-architecture/index.html",
    "docs/03-domain/index.html",
    "docs/04-api/contract.html",
    "docs/04-api/index.html",
    "docs/05-database/index.html",
    "docs/06-security/index.html",
    "docs/07-development/index.html",
    "docs/08-devops/index.html",
    "docs/09-testing/index.html",
    "docs/10-agents/index.html",
    "docs/11-integrations/index.html",
    "docs/12-ai/index.html",
    "docs/13-observability/index.html",
} | {f"docs/10-agents/{name}" for name in REQUIRED_PROMPTS}

OVERLAY_AGENT_DOCUMENTS = {
    ".agent/execution/current-context.html",
    ".agent/execution/sessions-history.html",
    ".agent/execution/task-board.html",
    ".agent/planning/dependency-graph.html",
    ".agent/planning/epics.html",
    ".agent/planning/milestones.html",
    ".agent/planning/roadmap.html",
    ".agent/intelligence/code-graph/api-routes.html",
    ".agent/intelligence/code-graph/database-usage.html",
    ".agent/intelligence/code-graph/dependencies.html",
    ".agent/intelligence/code-graph/function-map.html",
    ".agent/intelligence/code-graph/modules.html",
    ".agent/intelligence/git-nexus/commit-map.html",
    ".agent/intelligence/git-nexus/decision-commit-map.html",
    ".agent/intelligence/git-nexus/regression-log.html",
    ".agent/intelligence/git-nexus/task-commit-map.html",
} | {f".agent/templates/{name}" for name in REQUIRED_TEMPLATES}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


class Validator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.overlay_mode = (root / "AGENTIC-SDLC-KIT.html").exists()
        self.findings: list[Finding] = []
        self.metadata: dict[Path, dict[str, str]] = {}
        self._cache: dict[Path, tuple[dict[str, str], str, list[str]]] = {}

    def error(self, code: str, path: Path | str, message: str) -> None:
        if isinstance(path, Path):
            try:
                display = path.relative_to(self.root).as_posix()
            except ValueError:
                display = str(path)
        else:
            display = path
        self.findings.append(Finding(code, display, message))

    def document_files(self) -> list[Path]:
        if self.overlay_mode:
            files = {self.root / relative for relative in OVERLAY_DOCUMENTS | OVERLAY_AGENT_DOCUMENTS}
            for runtime_relative in (".agent/governance", ".agent/reports"):
                runtime_root = self.root / runtime_relative
                if runtime_root.exists():
                    files.update(runtime_root.rglob("*.html"))
            return sorted(path for path in files if path.exists())
        return sorted(
            path
            for path in self.root.rglob("*.html")
            if not any(part in SKIPPED_PARTS for part in path.relative_to(self.root).parts)
        )

    def parsed(self, path: Path) -> tuple[dict[str, str], str, list[str]]:
        if path not in self._cache:
            self._cache[path] = kit_html.read_document(path)
        return self._cache[path]

    def read(self, path: Path) -> str:
        """Văn bản theo quy ước kit (## heading, - **Field**: `v`, | bảng |) dựng từ HTML."""
        if path.suffix.lower() != ".html":
            return path.read_text(encoding="utf-8-sig")
        return self.parsed(path)[1]

    @staticmethod
    def headings(text: str) -> set[str]:
        return {match.group(1).strip() for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", text)}

    @staticmethod
    def field(text: str, name: str) -> str | None:
        match = re.search(rf"(?m)^- \*\*{re.escape(name)}\*\*:\s*`([^`]+)`\s*$", text)
        return match.group(1).strip() if match else None

    def validate_required_paths(self) -> None:
        required = COMMON_REQUIRED_PATHS | (OVERLAY_REQUIRED_PATHS if self.overlay_mode else DISTRIBUTION_REQUIRED_PATHS)
        for relative in sorted(required):
            if not (self.root / relative).exists():
                self.error("MISSING_REQUIRED_PATH", relative, "required packaging or operating asset is missing")

    def validate_frontmatter(self) -> None:
        ids: dict[str, Path] = {}
        for path in self.document_files():
            metadata, body, _links = self.parsed(path)
            if not metadata:
                self.error("METADATA_MISSING", path, 'file must declare <meta name="labelx:*"> metadata in <head>')
                continue
            self.metadata[path] = metadata

            for key in REQUIRED_METADATA:
                if not metadata.get(key, "").strip():
                    self.error("METADATA_MISSING", path, f"required metadata field '{key}' is missing or empty")

            document_id = metadata.get("id")
            if document_id:
                if document_id in ids:
                    other = ids[document_id].relative_to(self.root).as_posix()
                    self.error("DUPLICATE_ID", path, f"id '{document_id}' is already used by {other}")
                else:
                    ids[document_id] = path

            document_type = metadata.get("type")
            if document_type and document_type not in ALLOWED_TYPES:
                self.error("METADATA_TYPE_INVALID", path, f"unsupported type '{document_type}'")

            priority = metadata.get("priority", "")
            if priority and priority not in {"1", "2", "3", "4", "5"}:
                self.error("METADATA_PRIORITY_INVALID", path, "priority must be an integer from 1 through 5")

            tags = metadata.get("tags", "")
            if tags and not re.fullmatch(r"\[[^\[\]]+\]", tags):
                self.error("METADATA_TAGS_INVALID", path, "tags must use a non-empty inline YAML list")

            if not body.strip():
                self.error("DOCUMENT_BODY_EMPTY", path, "document body must not be empty")

    def validate_internal_links(self) -> None:
        for path in self.document_files():
            for raw_target in self.parsed(path)[2]:
                target = raw_target.strip()
                if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "//")):
                    continue
                target = unquote(target).split("#", 1)[0].split("?", 1)[0]
                if not target or "<" in target or ">" in target:
                    continue
                resolved = (self.root / target.lstrip("/")) if target.startswith("/") else (path.parent / target)
                if not resolved.resolve().exists():
                    self.error("INTERNAL_LINK_BROKEN", path, f"link target does not exist: {target}")

    def validate_templates(self) -> None:
        directory = self.root / ".agent" / "templates"
        actual = {path.name for path in directory.glob("*.html")} if directory.exists() else set()
        for name in sorted(REQUIRED_TEMPLATES - actual):
            self.error("TEMPLATE_MISSING", directory / name, "required reusable template is missing")
        for name in sorted(actual - REQUIRED_TEMPLATES):
            self.error("TEMPLATE_UNEXPECTED", directory / name, "unregistered template requires governed framework update")

        for path in directory.glob("*.html") if directory.exists() else []:
            missing = COMMON_TEMPLATE_HEADINGS - self.headings(self.read(path))
            for heading in sorted(missing):
                self.error("TEMPLATE_HEADING_MISSING", path, f"required stable heading is missing: {heading}")

        for path in (path for path in self.document_files() if "template" in path.name.lower()):
            if path.parent != directory:
                self.error("TEMPLATE_PLACEMENT_INVALID", path, "reusable templates must be stored in .agent/templates")

    def validate_prompts(self) -> None:
        directory = self.root / "docs" / "10-agents"
        actual = {path.name for path in directory.glob("*-prompt.html")} if directory.exists() else set()
        for name in sorted(REQUIRED_PROMPTS - actual):
            self.error("PROMPT_MISSING", directory / name, "required agent prompt is missing")
        for path in directory.glob("*-prompt.html") if directory.exists() else []:
            missing = PROMPT_HEADINGS - self.headings(self.read(path))
            for heading in sorted(missing):
                self.error("PROMPT_HEADING_MISSING", path, f"required prompt heading is missing: {heading}")

    def validate_runtime_placement(self) -> None:
        governance = self.root / ".agent" / "governance"
        reports = self.root / ".agent" / "reports"
        for root, expected_type in ((governance, "governance"), (reports, "report")):
            for path in root.rglob("*") if root.exists() else []:
                if not path.is_file() or path.name == ".keep":
                    continue
                if path.suffix.lower() != ".html":
                    self.error("RUNTIME_FILE_INVALID", path, "runtime governance and report records must be HTML or .keep")
                    continue
                if "template" in path.name.lower():
                    self.error("RUNTIME_TEMPLATE_MISUSE", path, "runtime directories must not contain reusable templates")
                if path.parent == root:
                    self.error("RUNTIME_PLACEMENT_INVALID", path, "runtime record must be stored in a category directory")
                metadata = self.metadata.get(path, {})
                if metadata.get("type") != expected_type:
                    self.error("RUNTIME_TYPE_INVALID", path, f"runtime record type must be '{expected_type}'")
                if re.search(r"<required[^>]*>", self.read(path), re.IGNORECASE):
                    self.error("RUNTIME_PLACEHOLDER_FOUND", path, "runtime record contains an unresolved required placeholder")

                category = path.parent.name
                allowed = RUNTIME_STATUSES.get(category)
                status = self.field(self.read(path), "Status")
                if allowed and status not in allowed:
                    self.error("RUNTIME_STATUS_INVALID", path, f"status '{status}' is invalid for {category}")

    @staticmethod
    def table_records(text: str, prefix: str) -> list[list[str]]:
        records: list[list[str]] = []
        for line in text.splitlines():
            if re.match(rf"^\|\s*`{re.escape(prefix)}", line):
                records.append([cell.strip().strip("`") for cell in line.strip().strip("|").split("|")])
        return records

    def validate_record_statuses(self) -> None:
        specifications = (
            (".agent/planning/roadmap.html", "R-", 4, ROADMAP_STATUSES),
            (".agent/planning/milestones.html", "M-", 5, MILESTONE_STATUSES),
            (".agent/planning/epics.html", "E-", 4, EPIC_STATUSES),
            (".agent/execution/task-board.html", "T-", 4, TASK_STATUSES),
            (".agent/planning/dependency-graph.html", "EDGE-", 5, EDGE_STATUSES),
            (".agent/execution/sessions-history.html", "S", 5, SESSION_OUTCOMES),
        )
        for relative, prefix, status_index, allowed in specifications:
            path = self.root / relative
            if not path.exists():
                continue
            for row in self.table_records(self.read(path), prefix):
                if len(row) <= status_index:
                    self.error("RECORD_SCHEMA_INVALID", path, f"record '{row[0]}' has too few table columns")
                elif row[status_index] not in allowed:
                    self.error("LIFECYCLE_STATUS_INVALID", path, f"record '{row[0]}' has invalid status '{row[status_index]}'")

        context_path = self.root / ".agent" / "execution" / "current-context.html"
        if context_path.exists():
            text = self.read(context_path)
            context_status = self.field(text, "Context Status")
            roadmap_status = self.field(text, "Planning Roadmap Status")
            if context_status not in CONTEXT_STATUSES:
                self.error("CONTEXT_STATUS_INVALID", context_path, f"invalid context status '{context_status}'")
            if roadmap_status and roadmap_status not in ROADMAP_STATUSES:
                self.error("ROADMAP_STATUS_INVALID", context_path, f"invalid roadmap status '{roadmap_status}'")

    def validate_lifecycle_consistency(self) -> None:
        for relative, expected_values in EXPECTED_ENUM_LINES.items():
            path = self.root / relative
            if not path.exists():
                continue
            text = self.read(path)
            for expected in expected_values:
                if expected not in text:
                    self.error("LIFECYCLE_ENUM_MISMATCH", path, f"expected enum is missing: {expected}")

        agent_path = self.root / "AGENT.html"
        if agent_path.exists():
            text = self.read(agent_path)
            if re.search(r"(?im)^##\s+Required Reading Order\s*$", text) or re.search(r"(?im)^-\s+Always load\s+", text):
                self.error("FIXED_READING_ORDER", agent_path, "context retrieval must remain task-driven")
            if "Context retrieval is task-driven" not in text:
                self.error("TASK_DRIVEN_RETRIEVAL_MISSING", agent_path, "task-driven retrieval rule is missing")

    def validate_dependencies(self) -> None:
        path = self.root / ".agent" / "planning" / "dependency-graph.html"
        if not path.exists():
            return
        rows = self.table_records(self.read(path), "EDGE-")
        graph: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            if len(row) < 6:
                continue
            dependent, prerequisite, status = row[1], row[2], row[5]
            if dependent == prerequisite:
                self.error("DEPENDENCY_SELF_REFERENCE", path, f"{row[0]} is self-referential")
            if status != "removed":
                graph[dependent].add(prerequisite)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(next_node) for next_node in graph.get(node, set())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        if any(visit(node) for node in list(graph)):
            self.error("DEPENDENCY_CYCLE", path, "active dependency graph contains a directed cycle")

    def validate_packaging_contract(self) -> None:
        readme = self.root / ("AGENTIC-SDLC-KIT.html" if self.overlay_mode else "README.md")
        required_readme_headings = {
            "Core Concepts",
            "Folder Structure",
            "Agent Roles",
            "Workflow Overview",
            "Context Retrieval Model",
            "Planning Lifecycle",
            "Governance Model",
            "Quick Start",
            "Project Onboarding Flow",
        }
        if readme.exists():
            missing = required_readme_headings - self.headings(self.read(readme))
            for heading in sorted(missing):
                self.error("README_SECTION_MISSING", readme, f"required packaging section is missing: {heading}")

    def validate_installer_contract(self) -> None:
        installer_paths = [self.root / "scripts" / "install-kit.ps1", self.root / "scripts" / "install-kit.sh"]
        whole_agent_patterns = [
            r"Copy-DirectoryAsset\s+-SourceRelative\s+['\"]\.agent['\"]\s+-DestinationRelative\s+['\"]\.agent['\"]",
            r"copy_directory_asset\s+['\"]\.agent['\"]\s+['\"]\.agent['\"]",
            r"cp\s+-a\s+['\"]?\$KIT_ROOT/\.agent",
            r"Copy-Item\b[^\n\r]+\.agent\b[^\n\r]+-Recurse",
        ]
        runtime_record_patterns = [
            r"\.agent[/\\]reports[/\\][^\n\r'\"\s]+\.(md|html)",
            r"\.agent[/\\]governance[/\\][^\n\r'\"\s]+\.(md|html)",
            r"Copy-DirectoryAsset\s+-SourceRelative\s+['\"]\.agent[/\\]reports",
            r"Copy-DirectoryAsset\s+-SourceRelative\s+['\"]\.agent[/\\]governance",
            r"copy_directory_asset\s+['\"]\.agent[/\\]reports",
            r"copy_directory_asset\s+['\"]\.agent[/\\]governance",
        ]
        for path in installer_paths:
            if not path.exists():
                continue
            text = self.read(path)
            for pattern in whole_agent_patterns:
                if re.search(pattern, text):
                    self.error(
                        "INSTALLER_WHOLE_AGENT_COPY",
                        path,
                        "installer must not copy the entire .agent directory; copy reusable assets and initialize clean runtime state",
                    )
            for pattern in runtime_record_patterns:
                if re.search(pattern, text):
                    self.error(
                        "INSTALLER_RUNTIME_RECORD_COPY",
                        path,
                        "installer must not copy runtime .agent/reports or .agent/governance records",
                    )

    def run(self) -> list[Finding]:
        self.validate_required_paths()
        self.validate_frontmatter()
        self.validate_internal_links()
        self.validate_templates()
        self.validate_prompts()
        self.validate_runtime_placement()
        self.validate_record_statuses()
        self.validate_lifecycle_consistency()
        self.validate_dependencies()
        self.validate_packaging_contract()
        self.validate_installer_contract()
        return sorted(self.findings, key=lambda item: (item.path, item.code, item.message))


def main() -> int:
    validator = Validator(ROOT)
    findings = validator.run()
    for finding in findings:
        print(f"ERROR [{finding.code}] {finding.path}: {finding.message}")
    if findings:
        print("FRAMEWORK_VALIDATION_FAIL")
        return 1
    print("FRAMEWORK_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
