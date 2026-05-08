# Dorje — Architecture

Folder-level semantic search CLI. Indexes code, text files, and git history. Searches across all of them uniformly.

## Design Principles

- **Agents first, humans welcome.** JSON output by default (`--json`), clean readable text otherwise. No hand-holding.
- **Search is search.** The user asks a question. Dorje figures out whether the answer is in a file, a function signature, or a commit from six months ago.
- **Own the storage.** Numpy-based vector storage in a simple format we control. No external vector DB dependency. Enables merge, split, sync between indexes.
- **Plugin architecture for language support.** Each language gets a parser module behind a common interface. Same pattern as linting tools.
- **LLM-enrichment is optional.** AST parsing is the foundation. LLM analysis (summaries, structural diffs) is user-configurable.

## CLI Interface

```
dorje index [path]              # Build index for a directory
dorje update [path]             # Incremental update — only changed files and new commits
dorje search "query"            # Search across everything indexed
dorje config                    # Manage settings (API keys, model endpoints, etc.)
```

`dorje update` detects changes (file hashes, git HEAD), re-indexes only what's dirty,
and propagates updates through the partition structure. Works across the delegation tree —
updates leaf indexes, then updates parent pointers if needed.

### Global Flags

| Flag                    | Description                                      |
|-------------------------|--------------------------------------------------|
| `--json`                | Structured JSON output (default for piped stdout) |
| `--enumerate-to-leaves` | List all leaf indexes in the index tree           |
| `--populate-leaves`     | Split index into child `.dorje/` dirs matching tree structure |
| `--to-mermaid`          | Output the knowledge graph as a Mermaid diagram (supports path filter) |
| `--predict-impact`      | Trace impact of a described change through the dependency graph |

Indexes are distributed — any folder can have its own `.dorje/`. Parent indexes delegate
to child indexes, never overlap. See **Storage** section for details.

### Exit Codes

| Code | Meaning           |
|------|--------------------|
| 0    | Success            |
| 1    | General error      |
| 2    | No results found   |
| 3    | Configuration error |

Stdin supported — queries can be piped in.

## Indexing Pipeline

```
Files/Repo
    |
    v
[1. Discovery] — Walk directory tree, identify file types, respect .gitignore + .dorjeignore
    |
    v
[2. Parsing] — Language-aware chunking via plugin parsers
    |
    v
[3. Embedding] — Vectorize chunks (model TBD — local or API)
    |
    v
[4. Storage] — Write vectors + metadata to local/global index
```

### Git History Pipeline

```
Git Log
    |
    v
[1. Extract] — Commits, diffs, metadata (author, date, files changed)
    |
    v
[2. Analyze] — AST-level diff analysis: renames, signature changes, structural shifts
    |        — Optional LLM enrichment: summaries, intent classification
    |
    v
[3. Embed] — Vectorize extracted information
    |
    v
[4. Storage] — Write to index alongside file content vectors
```

## Chunking Strategy

### Code Files
- Language-aware chunking via AST: functions, classes, methods as natural units.
- 8K token window. If a unit exceeds the window, stride with retained context from the top of the function/class.

### Non-Code Text Files (markdown, prose, etc.)
- Chunk by paragraphs.
- Minimum token count per chunk — fit at least that many paragraphs in.
- Maximum paragraphs per chunk.
- Stride between chunks for context continuity.

### Git Diffs
- Per-commit chunks containing: message, structured diff analysis, metadata.
- Structural changes (renames, signature changes) extracted and stored as discrete searchable units.

## Search

Three search modalities, fused at query time:

### 1. Vector Search (Semantic)
- Numpy-based cosine similarity.
- Query embedding matched against all indexed vectors.
- Sufficient for <100K vectors. FAISS is the escape hatch if needed later.

### 2. BM25 (Keyword)
- Full-text keyword search over raw chunk content.
- Handles exact matches, identifiers, error messages — things semantic search fumbles.

### 3. Graph Search (Knowledge Graph)
- A knowledge graph of `(subject, verb, object)` triples.
- Two layers:
  - **AST layer** (always present, deterministic): calls, imports, inheritance, contains.
  - **Semantic layer** (LLM-enriched, optional): features, concepts, intent. e.g., `(Feature: "authentication", uses, validate_token)`.
- Nodes are anything — functions, modules, classes, but also abstract concepts ("caching", "error handling").
- Verbs are freeform strings — "calls", "depends on", "implements", "validates against".
- All three parts of each triple (subject, verb, object) are embedded as vectors.
- Graph queries are semantic: "what depends on auth" matches verbs like "uses", "requires", "imports from" via vector similarity on the verb.
- Stored as adjacency lists in msgpack, loaded into memory for queries, unloaded when done.

### Result Ranking

The query itself determines how results from different modalities and sources (files vs. git history) are weighted. An LLM-compatible API endpoint classifies query intent and adjusts ranking accordingly. This is the core "AI" value — the user just asks a question, and Dorje decides where to look and how to rank.

## Storage

### Index Format

### Distributed Index Tree

Any folder can have its own `.dorje/` index. Each index declares the subtree it covers
in its `scope.json`. A parent index does **not** re-index subtrees that have their own index —
it points to them instead. No overlap, no duplication.

```
project/
  .dorje/                  # Covers project/, excluding src/auth/ and lib/
    scope.json             # {"covers": ".", "delegates": ["src/auth", "lib"]}
    ...
  src/
    auth/
      .dorje/              # Covers src/auth/ only
        scope.json         # {"covers": ".", "delegates": []}
        ...
  lib/
    .dorje/                # Covers lib/ only
      scope.json
      ...
```

**Search** walks up from the query location to find the nearest index, then follows
delegation pointers to query child indexes as needed.

**`--enumerate-to-leaves`** walks the full index tree and lists all leaf indexes.

**`--populate-leaves`** splits a parent index into child `.dorje/` directories matching
the tree structure. This is a file copy — no re-indexing, no re-embedding.

### Index Contents

Data is **partitioned by path prefix** within each index. This is the key invariant that
makes `--populate-leaves` a simple file copy.

```
.dorje/
  scope.json           # Subtree coverage and delegation pointers
  config.json          # Index-specific settings
  partitions/
    <path-hash>/       # One partition per covered subtree
      content_vectors.npy   # Content embedding vectors (float16)
      metadata_vectors.npy  # Metadata embedding vectors (float16)
      chunks.json           # Chunk metadata (file, line range, type, AST context)
      bm25.msgpack     # BM25 inverted index for this subtree
      graph/
        nodes.msgpack  # Graph nodes
        triples.msgpack
        node_vectors.npy
        verb_vectors.npy
      git/
        commits.json   # Processed commit data
        vectors.npy    # Commit/diff vectors
```

Each partition maps to a directory subtree. `--populate-leaves` moves partitions into
their own `.dorje/` at the target directory and updates `scope.json` delegation pointers.

Format is intentionally simple — numpy arrays + JSON/msgpack. We own the format,
so distributed operations are straightforward.

### Incremental Indexing

- Track file hashes and git HEAD position.
- On re-index, only process changed files and new commits.
- Deleted files are pruned from the index.

## Language Parser Plugin Architecture

```python
class LanguageParser(Protocol):
    """Interface that every language parser must implement."""

    name: str
    extensions: list[str]

    def parse(self, source: str, path: str) -> list[Chunk]:
        """Parse source code into semantic chunks (functions, classes, etc.)."""
        ...

    def build_graph(self, source: str, path: str) -> list[GraphNode]:
        """Extract graph nodes and edges (calls, imports, inheritance)."""
        ...
```

Launch languages (top 5 by current popularity):
- Python
- JavaScript / TypeScript
- Java
- C / C++
- Go

Adding a new language = implementing the `LanguageParser` interface and registering it.

## LLM Integration

All LLM calls go through an OpenAI-compatible API. This covers:
- OpenAI
- Ollama
- LM Studio
- vLLM
- Together, Groq, Mistral, etc.

LLM is used for:
- **Git diff analysis** (optional): Summarize commits, classify intent, describe structural changes.
- **Query intent classification**: Determine how to weight search modalities and sources.
- **Result ranking**: Re-rank results based on query context.

Configured via `dorje config` — endpoint URL, model name, API key.

## Embedding Model

TBD — depends on local vs. API tradeoff. Candidates:
- **Jina Embeddings v4**: Open weights, 3B params, 2048-dim (truncatable to 128), multimodal.
- **Nomic Embed Multimodal**: Open source, strong on PDFs/charts.
- **Gemini Embedding 2**: API-only, natively multimodal, 8K context.

Architecture is model-agnostic — embedding is behind an interface, swappable.

## Dependencies (Minimal)

```
numpy           # Vector storage and similarity
tiktoken        # Token counting
tree-sitter     # AST parsing (multi-language)
rank-bm25       # BM25 search
openai          # LLM API client (OpenAI-compatible)
```

No vector DB. No heavy frameworks. No CLI bling.

## File Type Support

Phase 1: Anything stored internally as text.
- Code (all languages with a registered parser, plus fallback line-based chunking)
- Markdown
- Plain text
- Config files (JSON, YAML, TOML, etc.)

Phase 2: Extend to other common non-proprietary formats as needed.
