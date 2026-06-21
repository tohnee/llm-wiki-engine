"""领域数据模型。

两层不变量:
- 导航层(Fact / Entity / Relation / WikiNode)可有损,只用于"答案在哪"。
- 证据层(Span)无损,是唯一 citation 落点,回答"答案是什么"。
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class CompileDepth(str, Enum):
    D0 = "D0"   # fast: parse + chunk/span + embedding + 路由摘要
    D1 = "D1"   # standard: D0 + fact/entity + resolution
    D2 = "D2"   # graph: D1 + relation + 跨文档链接 + wiki render


class DocStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    QUERYABLE_COARSE = "queryable_coarse"  # D0 完成,可问(纯 span 检索)
    QUERYABLE_FULL = "queryable_full"      # D1/D2 完成
    FAILED = "failed"


class SpanType(str, Enum):
    TEXT = "text"
    TABLE_ROW = "table_row"
    FORMULA = "formula"
    FIGURE_CAPTION = "figure_caption"


class Provenance(str, Enum):
    """认识论状态(借自 obsidian-wiki)。"""
    EXTRACTED = "extracted"   # 源文明确陈述
    INFERRED = "inferred"     # AI 跨源推理,无单一来源直接说
    AMBIGUOUS = "ambiguous"   # 多来源互相矛盾


class Tier(str, Enum):
    """重要度分层,用于检索排序与读取预算(借自 obsidian-wiki)。"""
    CORE = "core"
    SUPPORTING = "supporting"
    PERIPHERAL = "peripheral"


# ---------------- 证据层 ----------------

class Span(BaseModel):
    """证据原子。citation 的最终落点。100~300 token。"""
    span_id: str
    chunk_id: str
    document_id: str
    tenant_id: str
    content: str
    page: int
    bbox: Optional[tuple[float, float, float, float]] = None  # MinerU 版面坐标,原文高亮回链
    span_type: SpanType = SpanType.TEXT
    embedding: Optional[list[float]] = None


class Chunk(BaseModel):
    """上下文单元(parent)。命中 span 后扩展到此提供上下文。800~1500 token。"""
    chunk_id: str
    tenant_id: str
    document_id: str
    content: str
    page_start: int
    page_end: int
    span_ids: list[str] = Field(default_factory=list)
    section_path: str = ""                 # "第3章 > 3.2 > 预算"
    content_hash: str = ""                  # 增量编译依据
    summary: str = ""                       # ≤200 字符,tier-0 摘要扫描用(借自 obsidian-wiki)
    tier: "Tier" = None                     # 重要度:core/supporting/peripheral


# ---------------- 导航层 ----------------

class Fact(BaseModel):
    """带 span provenance 的导航索引。永远不作为最终引用源。"""
    fact_id: str
    tenant_id: str
    document_id: str
    subject_entity: str                     # 指向 canonical entity_id(resolution 后)
    predicate: str
    object_value: str                       # 实体引用或字面值
    qualifiers: dict = Field(default_factory=dict)   # 时间/条件/单位等限定
    confidence: float = 1.0
    provenance: "Provenance" = None                  # extracted/inferred/ambiguous(借自 obsidian-wiki)
    contradicts: list[str] = Field(default_factory=list)  # 与之冲突的 fact_id(ambiguous 时填)
    # ---- 记忆生命周期(借自 llm-wiki v2:confidence/supersession/forgetting)----
    source_count: int = 1                            # 支持该事实的来源数(强化信号)
    created_at: float = 0.0                          # 首次写入时间戳
    last_confirmed: float = 0.0                      # 最近一次被来源确认
    retention: float = 1.0                           # Ebbinghaus 保留度(随时间衰减,强化重置)
    superseded_by: Optional[str] = None              # 被哪个 fact 取代(版本化)
    stale: bool = False                              # 是否已过时(保留但降权)
    source_span_ids: list[str] = Field(default_factory=list)  # ★ 强制回链原文
    source_hash: str = ""


class Entity(BaseModel):
    entity_id: str                          # canonical id
    tenant_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: str                               # org | person | product | project | concept | ...
    description: str = ""
    mention_span_ids: list[str] = Field(default_factory=list)  # 跨文档提及(多跳骨架)
    document_ids: list[str] = Field(default_factory=list)
    embedding: Optional[list[float]] = None  # 用于 entity resolution blocking


class Relation(BaseModel):
    relation_id: str
    tenant_id: str
    source_entity: str
    relation_type: str                      # works_for | owns | develops | depends_on | ...
    target_entity: str
    source_span_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class WikiNode(BaseModel):
    """仅视图。由 KG 渲染,非由原文渲染。禁止作为引用源。"""
    node_id: str
    tenant_id: str
    title: str
    content: str
    entity_id: Optional[str] = None
    children: list[str] = Field(default_factory=list)
    provenance_mix: dict = Field(default_factory=dict)  # {extracted:.., inferred:.., ambiguous:..} 比例
    tier: "Tier" = None


class Document(BaseModel):
    document_id: str
    tenant_id: str
    title: str
    source_uri: str                         # s3://.../xxx.pdf
    status: DocStatus = DocStatus.UPLOADED
    depth: CompileDepth = CompileDepth.D1
    page_count: int = 0


# ---------------- 检索/取证 DTO ----------------

class EvidenceSpan(BaseModel):
    """检索返回的证据条目。"""
    span_id: str
    document_id: str
    content: str
    page: int
    score: float
    section_path: str = ""


class Citation(BaseModel):
    doc_id: str
    span_id: str


class Claim(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    verified: Optional[bool] = None
