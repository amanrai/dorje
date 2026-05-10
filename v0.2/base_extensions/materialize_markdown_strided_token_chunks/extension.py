"""Placeholder Markdown strided-token chunk materializer."""

from __future__ import annotations

from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Placeholder materializer for Markdown strided-token chunk rows. Requires tokenizer integration before use.", requires="derivative:text/markdown|text/plain", produces="chunks/chunks_fts")
def materialize_markdown_strided_token_chunks(handle: str, window_tokens: int = 512, stride_tokens: int = 256, write_fts: bool = True) -> dict[str, object]:
    del write_fts
    if window_tokens <= 0 or stride_tokens <= 0:
        raise ValueError("window_tokens and stride_tokens must be positive")
    record = HandleStore().get(handle)
    if record.kind != "derivative" or record.content_type not in ("text/markdown", "text/plain"):
        raise ValueError("materialize_markdown_strided_token_chunks requires a text/markdown or text/plain derivative handle")
    raise NotImplementedError("strided token materialization requires tokenizer integration")
