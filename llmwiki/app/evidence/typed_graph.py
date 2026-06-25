"""Typed knowledge graph helpers.

Obsidian-style backlinks only say "related".  This module upgrades relation handling to
an ontology-constrained typed graph so agents can traverse *how* entities are related:
uses / depends_on / contradicts / caused_by / fixed_by / superseded_by / etc.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

CORE_RELATION_TYPES = {
    "uses", "depends_on", "contradicts", "caused_by", "fixed_by", "superseded_by",
}
STRUCTURAL_RELATION_TYPES = {
    "references", "related_to", "works_for", "owns", "develops", "belongs_to", "part_of",
    "causes", "co_mention",
}
ALLOWED_RELATION_TYPES = CORE_RELATION_TYPES | STRUCTURAL_RELATION_TYPES
ACYCLIC_RELATION_TYPES = {"depends_on", "caused_by", "superseded_by"}

_RELATION_ALIASES = {
    "use": "uses",
    "using": "uses",
    "used_by": "uses",
    "depends": "depends_on",
    "depends on": "depends_on",
    "dependency": "depends_on",
    "blocks": "depends_on",
    "blocked_by": "depends_on",
    "contradict": "contradicts",
    "conflicts_with": "contradicts",
    "conflict": "contradicts",
    "caused by": "caused_by",
    "causes": "causes",
    "cause": "causes",
    "fixes": "fixed_by",
    "fixed by": "fixed_by",
    "resolved_by": "fixed_by",
    "replaced_by": "superseded_by",
    "supersedes": "superseded_by",
    "superseded by": "superseded_by",
    "reference": "references",
    "relates_to": "related_to",
    "related": "related_to",
}


@dataclass(frozen=True)
class RelationSpec:
    relation_type: str
    inverse: str | None = None
    acyclic: bool = False
    symmetric: bool = False
    description: str = ""


RELATION_SPECS: dict[str, RelationSpec] = {
    "uses": RelationSpec("uses", inverse="used_by", description="source uses target as a tool/resource"),
    "depends_on": RelationSpec("depends_on", inverse="required_by", acyclic=True, description="source requires target"),
    "contradicts": RelationSpec("contradicts", symmetric=True, description="claims/entities disagree"),
    "caused_by": RelationSpec("caused_by", inverse="causes", acyclic=True, description="source was caused by target"),
    "fixed_by": RelationSpec("fixed_by", inverse="fixes", description="source issue is fixed by target"),
    "superseded_by": RelationSpec("superseded_by", inverse="supersedes", acyclic=True, description="source is replaced by target"),
    "references": RelationSpec("references", description="source references target"),
    "related_to": RelationSpec("related_to", symmetric=True, description="weak fallback relation"),
    "works_for": RelationSpec("works_for"),
    "owns": RelationSpec("owns"),
    "develops": RelationSpec("develops"),
    "belongs_to": RelationSpec("belongs_to"),
    "part_of": RelationSpec("part_of"),
    "causes": RelationSpec("causes", inverse="caused_by", acyclic=True),
    "co_mention": RelationSpec("co_mention", symmetric=True),
}


def normalize_relation_type(value: str | None) -> str:
    """Return a safe ontology relation type; unknown values become related_to."""
    raw = (value or "").strip().lower().replace("-", "_")
    raw = re.sub(r"\s+", " ", raw)
    raw = _RELATION_ALIASES.get(raw, raw.replace(" ", "_"))
    raw = re.sub(r"[^a-z0-9_]", "", raw)
    return raw if raw in ALLOWED_RELATION_TYPES else "related_to"


def relation_spec(value: str | None) -> RelationSpec:
    return RELATION_SPECS[normalize_relation_type(value)]


def relation_type_prompt() -> str:
    """Compact prompt fragment used by relation extraction."""
    return " / ".join(sorted(ALLOWED_RELATION_TYPES))


def path_explain(edges: list[dict]) -> list[str]:
    """Human-readable path explanation for agent/tool responses."""
    out = []
    for e in edges:
        rel = normalize_relation_type(e.get("relation") or e.get("relation_type"))
        out.append(f"{e.get('source')} -[{rel}]-> {e.get('target')}")
    return out
