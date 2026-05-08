"""Named Pydantic response schemas for structured LM output."""

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Base class for strict response schemas."""

    model_config = ConfigDict(extra="forbid")


class SearchPlan(StrictSchema):
    """Plan for routing a user query across search systems."""

    intent: Literal["lookup", "explain", "impact", "summarize", "unknown"]
    bm25_query: str = Field(description="Lexical query for FTS/BM25.")
    vector_query: str = Field(description="Semantic query for vector search.")
    graph_needed: bool
    relational_filters: list[str] = Field(default_factory=list)


class AnswerCheck(StrictSchema):
    """Small structured answer with confidence."""

    answer: str
    confidence: Literal["low", "medium", "high"]
    caveats: list[str] = Field(default_factory=list)


class EntityExtraction(StrictSchema):
    """Code/search entities extracted from text."""

    symbols: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class RDFTriple(StrictSchema):
    """One subject-predicate-object fact extracted from text."""

    subject: str = Field(description="Entity/node id for the subject.")
    predicate: str = Field(description="Relationship or property name.")
    object: str = Field(description="Object node id or literal value.")
    object_type: Literal["node", "text", "int", "float", "bool", "json"]
    evidence: str = Field(description="Short source quote supporting the triple.")


class RDFExtract(StrictSchema):
    """Structured RDF-style facts extracted from a document."""

    document_title: str
    triples: list[RDFTriple] = Field(default_factory=list)


ResponseSchema: TypeAlias = type[StrictSchema]

_RESPONSE_SCHEMAS: dict[str, ResponseSchema] = {
    "answer_check": AnswerCheck,
    "entity_extraction": EntityExtraction,
    "rdf_extract": RDFExtract,
    "search_plan": SearchPlan,
}


def list_response_schemas() -> tuple[str, ...]:
    """Return available response schema names."""
    return tuple(sorted(_RESPONSE_SCHEMAS))


def get_response_schema(name: str) -> ResponseSchema:
    """Return a response schema class by name."""
    return _RESPONSE_SCHEMAS[name]
