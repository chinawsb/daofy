"""Public MCP resource registry for Daofy agent-facing documentation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class PublicResourceSpec:
    """A stable MCP resource backed by one or more repository files."""

    uri: str
    name: str
    title: str
    description: str
    mime_type: str
    relative_paths: tuple[str, ...]


@dataclass(frozen=True)
class PublicResourceMetadata:
    """Resolved metadata for a public MCP resource."""

    spec: PublicResourceSpec
    path: Path
    source: str
    byte_size: int
    sha256: str
    version: str
    updated: str


PUBLIC_RESOURCE_SPECS: tuple[PublicResourceSpec, ...] = (
    PublicResourceSpec(
        uri="delphi://coding-rules",
        name="CODING_RULES",
        title="Delphi coding rules",
        description="Delphi source coding, editing, compile, review, and automation rules.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/delphi/index.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/workflow",
        name="automation-workflow",
        title="Delphi automation workflow",
        description="Skill-style workflow for source-aware Delphi automation testing.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/workflow.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/script-generation-workflow",
        name="automation-script-generation-workflow",
        title="AI script generation workflow",
        description="Complete AI-facing process for generating executable Delphi automation scripts.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/script-generation-workflow.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/script-schema",
        name="automation-script-schema",
        title="Automation script schema",
        description="JSON step schema and assert_expr rules for automate_delphi GUI scripts.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/script-schema.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/report-schema",
        name="automation-report-schema",
        title="Automation report schema",
        description="Structured report fields returned by automate_delphi and how to interpret them.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/report-schema.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/repair-loop",
        name="automation-repair-loop",
        title="Automation repair loop",
        description="Failure diagnosis, script-vs-code decision, coding-mode switch, and rerun flow.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/repair-loop.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/inline-unit",
        name="automation-inline-unit",
        title="Delphi inline automation units",
        description="How Delphi projects wire in tools/auto units and the named-pipe protocol notes.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/inline-unit.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/index",
        name="automation-index",
        title="Automation testing index",
        description="Entry point for Delphi automation testing: directory structure, file index, scenario templates.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/index.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/architecture",
        name="automation-architecture",
        title="Automation testing architecture",
        description="Core methodology: RTTI/OCR decision matrix, perceive-plan-execute-verify loop, planning methodology, code-aware testing, experience loop, script cache management.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/architecture.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/uia-commands",
        name="automation-uia-commands",
        title="UIAutomation command reference",
        description="Complete UIAutomation command reference: click, value, navigation, window operations, scrolling, property reading, screenshot, wait, target finding.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/uia-commands.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/capability-matrix",
        name="automation-capability-matrix",
        title="Automation capability selection matrix",
        description="Scene-to-command mapping tables: Delphi controls, system dialogs, cross-process, browser, list/tree, validation, priority quick reference.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/capability-matrix.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/rtti-ocr-matrix",
        name="automation-rtti-ocr-matrix",
        title="RTTI vs OCR decision matrix",
        description="Functional verification vs visual integrity verification scene comparison table: when to use RTTI (rget/rinspect/dumpstate) vs OCR (capture/recognize) vs msgscan.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/rtti-ocr-matrix.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/planning-methodology",
        name="automation-planning-methodology",
        title="Automation planning methodology",
        description="Layered degradation strategy, action sequence specification, failure handling modes for automation test planning.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/planning-methodology.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/experience-loop",
        name="automation-experience-loop",
        title="Experience-driven optimization loop",
        description="Experience retrieval/save/merge mechanism: optimization cycle, search strategy, experience fusion principles.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/experience-loop.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/code-aware-testing",
        name="automation-code-aware-testing",
        title="Code-aware testing",
        description="Derive test paths and code-derived assertions from DFM/PAS source analysis: workflow, pattern mapping, assertion priorities.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/code-aware-testing.md",
        ),
    ),
    PublicResourceSpec(
        uri="delphi://automation/prompts",
        name="automation-prompts",
        title="Automation prompt templates",
        description="Reusable prompt templates for test planning, step execution protocol, failure recovery, experience saving, and MCP prompt catalog.",
        mime_type="text/markdown",
        relative_paths=(
            "src/resources/coding-rules/testing/automation/reference/prompts.md",
        ),
    ),
)


def resolve_resource_path(spec: PublicResourceSpec, root: Path | None = None) -> Path | None:
    """Return the first existing backing file for a resource spec."""
    base = root or PROJECT_ROOT
    for relative_path in spec.relative_paths:
        candidate = base / relative_path
        if candidate.exists():
            return candidate
    return None


def available_public_resources(root: Path | None = None) -> list[PublicResourceSpec]:
    """Return file-backed public resources available in the current installation."""
    return [
        spec for spec in PUBLIC_RESOURCE_SPECS
        if resolve_resource_path(spec, root=root) is not None
    ]


def _relative_source(path: Path, root: Path | None = None) -> str:
    """Return a display path relative to the resource root when possible."""
    base = root or PROJECT_ROOT
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _extract_document_metadata(text: str) -> tuple[str, str]:
    """Extract lightweight version and updated fields from a Markdown resource."""
    version = ""
    updated = ""
    for line in text.splitlines()[:20]:
        if "版本:" in line:
            match = re.search(r"版本:\s*([^|]+)", line)
            if match:
                version = match.group(1).strip()
        if "最后更新:" in line:
            match = re.search(r"最后更新:\s*([^|]+)", line)
            if match:
                updated = match.group(1).strip()
        if re.match(r"^\s*version\s*:", line, flags=re.IGNORECASE) and not version:
            version = line.split(":", 1)[1].strip()
        if re.match(r"^\s*updated\s*:", line, flags=re.IGNORECASE) and not updated:
            updated = line.split(":", 1)[1].strip()
    return version, updated


def get_public_resource_metadata(
    uri: str,
    root: Path | None = None,
) -> PublicResourceMetadata:
    """Resolve one public resource and return source metadata."""
    spec = next((item for item in PUBLIC_RESOURCE_SPECS if item.uri == uri), None)
    if spec is None:
        raise KeyError(uri)

    path = resolve_resource_path(spec, root=root)
    if path is None:
        raise FileNotFoundError(
            "No backing file found for {}. Checked: {}".format(
                uri,
                ", ".join(spec.relative_paths),
            )
        )

    data = path.read_bytes()
    text = data.decode("utf-8")
    version, updated = _extract_document_metadata(text)
    return PublicResourceMetadata(
        spec=spec,
        path=path,
        source=_relative_source(path, root=root),
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        version=version,
        updated=updated,
    )


def get_public_resource_text(uri: str, root: Path | None = None) -> tuple[str, str]:
    """Read a public resource by stable URI.

    Returns:
        Tuple of ``(mime_type, text)``.

    Raises:
        KeyError: if the URI is not a known public resource.
        FileNotFoundError: if the resource is known but no backing file exists.
    """
    metadata = get_public_resource_metadata(uri, root=root)
    return metadata.spec.mime_type, metadata.path.read_text(encoding="utf-8")


def build_public_resource_index(root: Path | None = None) -> str:
    """Build a compact Markdown index for AI agents."""
    lines = [
        "# Daofy Public MCP Resources",
        "",
        "Use these stable MCP resource URIs instead of reading client-specific hidden directories.",
        "",
        "| URI | Title | Source | Bytes | SHA-256 | Version | Updated | Description |",
        "|-----|-------|--------|-------|---------|---------|---------|-------------|",
    ]
    for spec in available_public_resources(root=root):
        metadata = get_public_resource_metadata(spec.uri, root=root)
        sha_short = metadata.sha256[:12]
        lines.append(
            "| `{}` | {} | `{}` | {} | `{}` | {} | {} | {} |".format(
                spec.uri,
                spec.title,
                metadata.source,
                metadata.byte_size,
                sha_short,
                metadata.version,
                metadata.updated,
                spec.description,
            )
        )
    return "\n".join(lines) + "\n"
