# Indexing Guidelines

Use this skill when the user asks Dorje to index, prepare, profile, search, or reason over a folder/corpus.

## Core Principle

Do not invent a hardcoded workflow. Compose primitives.

The indexing path should be discovered from the source handles, their media types, available converter tools, available collection tools, and the user's corpus-local hints.

## Process

1. **Ensure every source has a handle.**
   - First build or refresh the corpus source manifest.
   - Use the manifest builder / sync primitive when available.
   - The manifest should establish source handles for all discovered source content.
   - Source identity should be content-hash based where possible.

2. **Inspect the source handle collection.**
   - Determine what media types are present.
   - Examples: `text/html`, `application/pdf`, `text/markdown`, source code, images, audio, video.
   - Do not read full source contents into context unless explicitly needed for bounded inspection.

3. **Move sources toward an indexable state.**
   - Raw sources may need conversion before indexing.
   - HTML should usually become Markdown.
   - PDFs should usually become Markdown once a PDF-to-Markdown primitive exists.
   - Images, audio, and video need their own extraction primitives before they become indexable.
   - Markdown/plaintext is generally indexable.

4. **Use collection-aware primitives.**
   - If given a collection handle, prefer tools that accept and return collection handles.
   - Preserve provenance by deriving artifacts from immediate parent handles.
   - Do not duplicate full ancestry into every child; parent links are enough if handles persist.

5. **Chunk indexable text.**
   - Once content is in an indexable text state, chunk it with structure-aware chunking primitives.
   - For Markdown, use Markdown/paragraph/section-aware chunking.
   - Chunks should be handles or members of a collection, not copied into context.

6. **Send chunks to indexers.**
   - Once chunk collections exist, send each chunk or chunk collection to the appropriate indexer.
   - Future indexers may include BM25/FTS, vector, graph/entity, citation, or task-specific indexes.

7. **Report missing primitives.**
   - If the corpus contains sources that cannot yet be converted or indexed, say exactly what primitive is missing.
   - Example: "Need `pdf_to_md_handle` for application/pdf sources."
   - Example: "Need collection filtering by content_type before converting only HTML members."

## Current Gaps To Notice

When planning indexing, be aware that some required primitives may not exist yet. Obvious next primitives include:

- filter a collection by `content_type` / media type
- filter a collection by handle axes
- convert PDF handles to Markdown handles
- index Markdown chunk collections
- persist index metadata and stale/dirty state
- walk provenance chains

## Anti-Patterns

Avoid these:

- reading entire corpora into LM context
- treating all file types as directly indexable
- indexing raw HTML/PDF without considering conversion
- hardcoding a one-size-fits-all indexing workflow
- losing source/artifact provenance

## Preferred Shape

The preferred abstract shape is:

```text
corpus folder
  -> manifest / source handles
  -> source handle collection
  -> media/type-aware conversion to indexable artifact handles
  -> chunk collections
  -> index primitives
  -> searchable index artifacts
```

Use corpus-local hints to decide which index styles matter for the user's intent.
