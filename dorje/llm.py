"""LLM client — OpenAI-compatible API for optional enrichment and query classification."""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from dorje.config import LLMConfig

_MAX_RETRIES = 2
_MAX_TOKENS_RESPONSE = 1024


@dataclass(frozen=True, slots=True)
class QueryIntent:
    """Classified query intent with search weights."""

    intent_type: str  # "code", "history", "structural", "conceptual"
    content_weight: float
    metadata_weight: float
    bm25_weight: float
    graph_weight: float
    reasoning: str


# Default intents when LLM is not available
_INTENT_DEFAULTS: dict[str, QueryIntent] = {
    "code": QueryIntent(
        intent_type="code",
        content_weight=0.4,
        metadata_weight=0.25,
        bm25_weight=0.25,
        graph_weight=0.1,
        reasoning="Default code search weights",
    ),
    "history": QueryIntent(
        intent_type="history",
        content_weight=0.2,
        metadata_weight=0.2,
        bm25_weight=0.3,
        graph_weight=0.3,
        reasoning="Default history search weights",
    ),
    "structural": QueryIntent(
        intent_type="structural",
        content_weight=0.15,
        metadata_weight=0.15,
        bm25_weight=0.2,
        graph_weight=0.5,
        reasoning="Default structural search weights",
    ),
    "conceptual": QueryIntent(
        intent_type="conceptual",
        content_weight=0.35,
        metadata_weight=0.35,
        bm25_weight=0.15,
        graph_weight=0.15,
        reasoning="Default conceptual search weights",
    ),
}


class LLMClient:
    """LLM client for optional enrichment."""

    def __init__(self, config: LLMConfig) -> None:
        config.validate()
        self._config = config
        self._client: OpenAI | None = None

        if config.enabled:
            self._client = OpenAI(
                base_url=config.endpoint,
                api_key=config.auth_key or "unused",
            )

    @property
    def enabled(self) -> bool:
        """Whether LLM enrichment is enabled."""
        return self._config.enabled and self._client is not None

    def classify_query(self, query: str) -> QueryIntent:
        """Classify a search query to determine search weights.

        Falls back to heuristic classification if LLM is not available.
        """
        assert query, "query must not be empty"

        if not self.enabled:
            return _heuristic_classify(query)

        assert self._client is not None

        prompt = (
            "Classify this search query into one of: code, history, structural, conceptual.\n"
            "Respond with ONLY the category name, nothing else.\n\n"
            f"Query: {query}"
        )

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.0,
            )
            category = response.choices[0].message.content
            assert category is not None, "LLM returned empty response"
            category = category.strip().lower()

            if category in _INTENT_DEFAULTS:
                return _INTENT_DEFAULTS[category]

        except Exception:
            pass

        return _heuristic_classify(query)

    def summarize_diff(self, diff: str) -> str | None:
        """Summarize a git diff. Returns None if LLM is not available."""
        if not self.enabled:
            return None

        assert self._client is not None
        assert diff, "diff must not be empty"

        prompt = (
            "Summarize this code diff in 2-3 sentences. "
            "Focus on what changed structurally (renames, signature changes, "
            "new functions, removed functions).\n\n"
            f"```diff\n{diff[:4000]}\n```"
        )

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=_MAX_TOKENS_RESPONSE,
                temperature=0.0,
            )
            content = response.choices[0].message.content
            assert content is not None, "LLM returned empty response"
            return content.strip()
        except Exception:
            return None


    def answer_question(self, question: str, context_chunks: list[str]) -> str:
        """Answer a question using retrieved code chunks as context.

        Args:
            question: The user's question.
            context_chunks: List of code/text snippets to use as context.

        Returns:
            The LLM's answer string.
        """
        assert question, "question must not be empty"
        assert context_chunks, "context_chunks must not be empty"
        assert self.enabled, "LLM must be enabled for helpme"
        assert self._client is not None

        context = "\n\n---\n\n".join(context_chunks)

        # Truncate context to stay within reasonable limits
        max_context_chars = 12000
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n... (truncated)"

        prompt = (
            "You are a code assistant. Answer the question using ONLY the code context below.\n"
            "Be direct and concise. If the context doesn't contain enough information, say so.\n\n"
            f"--- CODE CONTEXT ---\n{context}\n--- END CONTEXT ---\n\n"
            f"Question: {question}"
        )

        response = self._client.chat.completions.create(
            model=self._config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_MAX_TOKENS_RESPONSE,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        assert content is not None, "LLM returned empty response"
        return content.strip()


def _heuristic_classify(query: str) -> QueryIntent:
    """Simple keyword-based query classification."""
    assert query, "query must not be empty"

    query_lower = query.lower()

    # Structural indicators
    structural_keywords = frozenset({
        "calls", "depends", "imports", "inherits", "uses",
        "what calls", "who calls", "what uses", "depends on",
        "impact", "affect",
    })

    # History indicators
    history_keywords = frozenset({
        "changed", "modified", "commit", "who changed", "when did",
        "history", "blame", "author", "last change", "recently",
    })

    # Check structural
    for kw in structural_keywords:
        if kw in query_lower:
            return _INTENT_DEFAULTS["structural"]

    # Check history
    for kw in history_keywords:
        if kw in query_lower:
            return _INTENT_DEFAULTS["history"]

    # Check if it looks like an identifier search (camelCase, snake_case, dots)
    has_identifier = any(
        c == "_" or c == "." for c in query
    ) or (any(c.isupper() for c in query) and any(c.islower() for c in query))

    if has_identifier:
        return _INTENT_DEFAULTS["code"]

    return _INTENT_DEFAULTS["conceptual"]
