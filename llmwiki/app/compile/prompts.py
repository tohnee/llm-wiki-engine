"""编译期 prompt。改这里要同步 bump config 里的 prompt_version,以触发选择性重编。"""

EXTRACT_SYSTEM = """你是知识编译器的抽取模块。从给定的文档片段中抽取原子事实(Fact)与实体(Entity)。

严格规则:
1. 只抽取片段中明确陈述的内容,不做任何推断或外部补充。
2. Fact 用 subject-predicate-object 三元组,并在 qualifiers 中保留时间、条件、单位、范围等限定语义(防止三元组丢失上下文)。
3. 每个 Fact 必须给出 source_span_index:它来自输入 spans 列表的哪个下标(可多个)。
4. Entity 给出 name、type(org/person/product/project/location/time/concept 之一)、出现的 span 下标。
5. 只输出 JSON,无任何额外文字、无 markdown 代码围栏。

输出格式:
{
  "facts": [
    {"subject":"", "predicate":"", "object":"", "qualifiers":{}, "source_span_index":[0]}
  ],
  "entities": [
    {"name":"", "type":"", "span_index":[0]}
  ]
}"""

RELATION_SYSTEM = """你从已抽取的实体与事实中归纳实体间关系。
关系类型限定:works_for / owns / develops / depends_on / references / belongs_to / part_of / causes。
每条关系必须标注支撑它的 span 下标。只输出 JSON:
{"relations":[{"source":"","relation_type":"","target":"","source_span_index":[0]}]}"""

WIKI_SYSTEM = """你是 Wiki 渲染器。输入是某实体的事实与关系集合(已带 span 引用)。
生成一篇结构化的中文 Wiki 节点(Overview/关键属性/关系/相关文档)。
重要:Wiki 仅作导航视图,不是引用源。每个事实陈述后用 [span:ID] 标注其证据 span,供下游回链。
只输出 markdown 正文。"""

RESOLVE_SYSTEM = """判断两个实体是否指代同一真实世界对象。
输入两个实体的 name、aliases、上下文描述。
只输出 JSON:{"merge": true/false, "canonical_name": "", "reason": ""}"""


# ---- Schema 感知的 prompt 构建器(把 TenantSchema 的类型/规则注入编译) ----

_DEFAULT_ENTITY_TYPES = ["org", "person", "product", "project", "location", "time", "concept"]
_DEFAULT_RELATION_TYPES = ["works_for", "owns", "develops", "depends_on", "references",
                           "belongs_to", "part_of", "causes"]


def build_extract_system(entity_types: list[str] | None = None, custom_rules: str = "") -> str:
    """用租户 schema 的实体类型表替换硬编码类型,附加自定义规则。"""
    types = entity_types or _DEFAULT_ENTITY_TYPES
    types_str = "/".join(types)
    system = EXTRACT_SYSTEM.replace(
        "org/person/product/project/location/time/concept 之一",
        f"{types_str} 之一")
    if custom_rules and custom_rules.strip():
        system += f"\n\n额外规则(租户自定义):\n{custom_rules.strip()}"
    return system


def build_relation_system(relation_types: list[str] | None = None, custom_rules: str = "") -> str:
    """用租户 schema 的关系类型表替换硬编码类型,附加自定义规则。"""
    types = relation_types or _DEFAULT_RELATION_TYPES
    types_str = " / ".join(types)
    system = RELATION_SYSTEM.replace(
        "works_for / owns / develops / depends_on / references / belongs_to / part_of / causes",
        types_str)
    if custom_rules and custom_rules.strip():
        system += f"\n\n额外规则(租户自定义):\n{custom_rules.strip()}"
    return system
