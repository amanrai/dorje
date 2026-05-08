# Dorje — Code Design

## Package Structure

```
dorje/
  __init__.py
  __main__.py              # Entry point: python -m dorje
  cli.py                   # argparse, dispatch

  # Core
  config.py                # Config loading/saving, defaults
  index.py                 # Index read/write/merge, incremental tracking
  storage.py               # Numpy vector storage, metadata, serialization

  # Indexing Pipeline
  discovery.py             # File walker, .gitignore respect, file type detection
  chunker.py               # Chunking orchestrator — delegates to parsers
  embedder.py              # Embedding client — OpenAI-compatible API

  # Search
  search.py                # Search orchestrator — fuses results from all modalities
  vector_search.py         # Numpy cosine similarity
  bm25_search.py           # BM25 keyword search
  graph_search.py          # Graph traversal queries

  # Git
  git.py                   # Git history extraction, diff parsing
  git_analysis.py          # Structural diff analysis (renames, signatures), optional LLM

  # Knowledge Graph
  graph.py                 # Graph construction — AST layer + LLM semantic layer
  graph_store.py           # Triple store — nodes, verbs, vectors, load/unload
  parsers/
    __init__.py            # Parser registry, LanguageParser protocol
    python.py
    javascript.py          # JS + TS
    java.py
    c.py                   # C + C++
    go.py
    fallback.py            # Line-based chunking for unrecognized languages

  # LLM
  llm.py                   # OpenAI-compatible client, query intent classification
```

## Concurrency Model

```
Worker pool: max(num_processors - 2, 1) * 2 workers
```

Multiprocessing, no shared memory. Work is divided at the file/chunk level.

### Indexing

```
CLI
 |
 v
discovery.py          # Single process: walk tree, produce file list
 |
 v
Pool.map              # Fan out: each worker parses + chunks a file
 |                      Workers call embedder client (HTTP) independently
 v
Index writer          # Single process: collect results, write to storage
```

Files are independent — no shared state needed between workers. Each worker:
1. Reads file
2. Selects parser from registry
3. Chunks
4. Sends chunks to embedding endpoint (OpenAI-compatible API)
5. Returns vectors + metadata

### Search

```
CLI
 |
 v
search.py             # Orchestrator
 |
 +--> vector_search   \
 +--> bm25_search      } -- Can run in parallel (ProcessPoolExecutor)
 +--> graph_search    /
 |
 v
Fusion + ranking      # Merge, deduplicate, rank
```

## Embedding Interface

Single interface, two backends. To the rest of the system, it's just a URL.

```python
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts. Returns (n, dim) array."""
        ...

    def dimension(self) -> int:
        """Return embedding dimension."""
        ...
```

Implementation is an HTTP client that POST's to an endpoint:

```
POST /embed
Authorization: Bearer <key>
Content-Type: application/json

{"texts": ["chunk1", "chunk2", ...]}

Response: {"vectors": [[0.1, 0.2, ...], ...]}
```

Uses the OpenAI-compatible `/v1/embeddings` endpoint. Works with Ollama, vLLM,
OpenAI, or any provider that implements the standard.

## Parser Registry

```python
# parsers/__init__.py

_REGISTRY: dict[str, type[LanguageParser]] = {}

def register(parser_cls: type[LanguageParser]) -> type[LanguageParser]:
    """Decorator to register a parser."""
    for ext in parser_cls.extensions:
        _REGISTRY[ext] = parser_cls
    return parser_cls

def get_parser(extension: str) -> LanguageParser:
    """Get parser for file extension, fallback to line-based."""
    cls = _REGISTRY.get(extension, FallbackParser)
    return cls()
```

Each parser module registers itself on import:

```python
# parsers/python.py

@register
class PythonParser:
    name = "python"
    extensions = [".py"]

    def parse(self, source: str, path: str) -> list[Chunk]:
        # tree-sitter AST -> functions, classes, methods
        ...

    def build_graph(self, source: str, path: str) -> list[GraphNode]:
        # imports, calls, inheritance
        ...
```

## AST-to-Chunk Pipeline

Full pipeline for turning source code into searchable, metadata-rich chunks.

```
Source File
    |
    v
[1. Parse] — tree-sitter produces concrete syntax tree
    |
    v
[2. Extract] — Walk AST, pull out structural units
    |            Functions, classes, methods, top-level statements, imports
    |
    v
[3. Contextualize] — For each unit, gather structural context from AST
    |                  Parent class/module, parameters, return type, decorators,
    |                  docstring, visibility, complexity
    |
    v
[4. Build Metadata] — Assemble a metadata record per chunk
    |                   This metadata is itself a searchable text blob
    |
    v
[5. Chunk] — Apply token limits, stride if unit exceeds window
    |
    v
[6. Embed] — Two vectors per chunk:
    |          (a) content vector — the raw code
    |          (b) metadata vector — the structured description
    |
    v
[7. Graph Extract] — From the same AST walk, emit nodes + triples
```

### Step 2: Structural Unit Extraction

tree-sitter node types extracted per language:

| Language   | Extracted Units                                                  |
|------------|------------------------------------------------------------------|
| Python     | `function_definition`, `class_definition`, `decorated_definition`|
| JS/TS      | `function_declaration`, `class_declaration`, `arrow_function`, `method_definition` |
| Java       | `method_declaration`, `class_declaration`, `interface_declaration`|
| C/C++      | `function_definition`, `struct_specifier`, `class_specifier`     |
| Go         | `function_declaration`, `method_declaration`, `type_declaration` |
| Fallback   | Line-based sliding window                                        |

Each unit includes its full body. Nested units (method inside class) are extracted
independently — the class chunk gets the class-level code (fields, docstring) without
method bodies; each method is its own chunk.

### Step 3: Contextualize

For each extracted unit, the parser walks the AST to gather:

```python
@dataclass(frozen=True, slots=True)
class ASTContext:
    name: str                    # "validate_token"
    qualified_name: str          # "auth.TokenValidator.validate_token"
    kind: str                    # "method"
    parent_name: str | None      # "TokenValidator"
    parent_kind: str | None      # "class"
    module_path: str             # "src/auth/validator.py"
    parameters: list[str]        # ["self", "token: str", "scope: list[str]"]
    return_type: str | None      # "bool"
    decorators: list[str]        # ["staticmethod"]
    docstring: str | None        # First docstring/comment block
    visibility: str              # "public", "private", "protected"
    complexity: int              # Cyclomatic complexity (count of branches)
    imports_used: list[str]      # Imports referenced within this unit
    calls_made: list[str]        # Functions/methods called within this unit
```

This is deterministic — pure AST, no LLM needed.

### Step 4: Build Metadata

The metadata record is assembled into a searchable text description:

```
function validate_token(self, token: str, scope: list[str]) -> bool
  in class TokenValidator
  in module src/auth/validator.py
  visibility: public
  decorators: none
  calls: decode_jwt, check_expiry, verify_scope
  imports used: jwt, datetime
  complexity: 4
  docstring: "Validate a JWT token against the required scope."
```

This text blob gets its own embedding vector. So a search for "JWT validation"
matches the metadata even if the code itself only says `decode(token)`.

**Two vectors per chunk:**
- `content_vector` — embedding of the raw source code
- `metadata_vector` — embedding of the structured metadata description

Search scores both and fuses them.

### Step 5: Chunking Rules

- If a unit fits within `max_tokens` (default 8192): one chunk.
- If it exceeds `max_tokens`: stride.
  - First chunk: full unit from start, up to `max_tokens`.
  - Subsequent chunks: retain the function/class signature + first N lines as
    context header, then continue from the stride point.
  - `stride_tokens` (default 256) controls overlap.
- Minimum token count per chunk enforced — tiny units (one-liners) are grouped
  with adjacent units in the same scope.

### Step 7: Graph Extraction

From the same AST walk, emit:

**Nodes:**
- Every extracted unit becomes a `GraphNode`.
- Module-level node for the file itself.

**Triples (AST layer):**
- `(function, calls, other_function)` — from `calls_made`
- `(module, imports, other_module)` — from import statements
- `(class, inherits, parent_class)` — from class definition
- `(class, contains, method)` — parent-child nesting
- `(function, uses_import, module)` — from `imports_used`

All edges are `source: "ast"`. LLM semantic triples are added in a separate
optional enrichment pass.

## Core Data Types

```python
@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    name: str | None                 # "validate_token"
    qualified_name: str | None       # "auth.TokenValidator.validate_token"
    kind: str                        # "function", "method", "class", "module", "paragraph"
    parent_name: str | None          # "TokenValidator"
    parent_kind: str | None          # "class"
    parameters: tuple[str, ...] | None   # ("self", "token: str", "scope: list[str]")
    return_type: str | None          # "bool"
    decorators: tuple[str, ...] | None   # ("staticmethod",)
    docstring: str | None            # First docstring/comment block
    visibility: str | None           # "public", "private", "protected"
    complexity: int | None           # Cyclomatic complexity
    imports_used: tuple[str, ...] | None # Imports referenced within this unit
    calls_made: tuple[str, ...] | None   # Functions/methods called within this unit

    def to_text(self) -> str:
        """Render as searchable text for metadata embedding."""
        ...

@dataclass(frozen=True, slots=True)
class Chunk:
    id: str                  # Deterministic hash of (path, start, end, content_hash)
    path: str                # File path relative to index root
    start_line: int
    end_line: int
    content: str             # Raw text
    chunk_type: str          # "function", "class", "paragraph", "commit", etc.
    language: str | None
    metadata: ChunkMetadata  # Structured metadata — also embedded as its own vector

@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk: Chunk
    score: float             # Fused score
    source: str              # "vector", "bm25", "graph"
    highlights: list[str]    # Relevant snippets for display

@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str                  # e.g., "module.Class.method" or "concept:authentication"
    kind: str                # "function", "class", "module", "import", "concept", "feature"
    label: str               # Human-readable name
    path: str | None         # File path (None for abstract concepts)
    line: int | None         # Line number (None for abstract concepts)
    metadata: dict           # Flexible

@dataclass(frozen=True, slots=True)
class Triple:
    subject: str             # Node id
    verb: str                # Freeform: "calls", "depends on", "implements", etc.
    object: str              # Node id
    source: str              # "ast" or "llm"
    bidirectional: bool      # True if relationship goes both ways (e.g., "sibling of")
    metadata: dict           # Flexible: confidence, context, etc.
```

All dataclasses use `frozen=True` and `slots=True` — immutable, cache-friendly, low memory.

## Storage Layout

```python
class IndexStore:
    """Manages reading/writing the .dorje/ index."""

    def __init__(self, path: Path):
        self.path = path

    # Vectors (two per chunk: content + metadata)
    def write_vectors(self, ids: list[str], content_vectors: np.ndarray, metadata_vectors: np.ndarray) -> None: ...
    def read_vectors(self, kind: str, slab_size: int | None = None) -> Iterator[tuple[list[str], np.ndarray]]:
        """Yield vectors in slabs. kind is 'content' or 'metadata'. If slab_size is None, yield all at once."""
        ...
    def delete_vectors(self, ids: list[str]) -> None: ...

    # Metadata
    def write_metadata(self, chunks: list[Chunk]) -> None: ...
    def read_metadata(self) -> list[Chunk]: ...

    # BM25
    def write_bm25_index(self, index: BM25Index) -> None: ...
    def read_bm25_index(self) -> BM25Index: ...

    # Graph
    def write_graph(self, nodes: list[GraphNode], triples: list[Triple]) -> None: ...
    def read_graph_nodes(self) -> list[GraphNode]: ...
    def read_graph_triples(self) -> list[Triple]: ...
    def read_graph_vectors(self, kind: str, slab_size: int | None = None) -> Iterator[tuple[list[str], np.ndarray]]:
        """Yield node or verb vectors in slabs. kind is 'node' or 'verb'."""
        ...

    # Incremental tracking
    def read_file_hashes(self) -> dict[str, str]: ...
    def write_file_hashes(self, hashes: dict[str, str]) -> None: ...
    def read_git_head(self) -> str | None: ...
    def write_git_head(self, sha: str) -> None: ...

    # Merge
    def merge_from(self, other: "IndexStore") -> None: ...
```

### File Formats

| File | Format | Why |
|------|--------|-----|
| `vectors/chunks.npy` | numpy `.npy` | Fast load, slab-based reads |
| `vectors/ids.json` | JSON array | Maps row index -> chunk id |
| `metadata.json` | JSON | Chunk metadata, human-inspectable |
| `bm25/index.msgpack` | msgpack | Faster than JSON for inverted index |
| `graph/nodes.msgpack` | msgpack | Graph nodes, compact |
| `graph/triples.msgpack` | msgpack | Subject-verb-object triples |
| `graph/node_vectors.npy` | numpy `.npy` | Vectors for node labels |
| `graph/verb_vectors.npy` | numpy `.npy` | Vectors for verb strings |
| `state.json` | JSON | File hashes, git HEAD, last index timestamp |

Numpy files are read in configurable slabs for memory control. At typical codebase scale
(few hundred thousand vectors), full load is fine. Slab-based reading provides a configurable
memory ceiling for larger indexes while maintaining exact (brute-force) search — no approximate
nearest neighbor tradeoffs. Precision is non-negotiable for code search.

## Search Fusion

```python
class SearchOrchestrator:
    def search(self, query: str, top_k: int = 20) -> list[SearchResult]:
        # 1. Classify query intent (LLM or heuristic fallback)
        intent = self.classify_query(query)

        # 2. Run search modalities in parallel
        with ProcessPoolExecutor(max_workers=3) as pool:
            vector_future = pool.submit(self.vector_search, query, top_k * 2)
            bm25_future = pool.submit(self.bm25_search, query, top_k * 2)
            graph_future = pool.submit(self.graph_search, query, top_k * 2)

        # 3. Fuse results with intent-driven weights
        weights = intent.weights  # e.g., {"vector": 0.5, "bm25": 0.3, "graph": 0.2}
        results = self.fuse(
            vector_future.result(),
            bm25_future.result(),
            graph_future.result(),
            weights,
        )

        # 4. Deduplicate, sort, truncate
        return self.dedupe_and_rank(results)[:top_k]
```

## Performance Considerations

- **Slab-based vector reads**: Vectors loaded in configurable slabs — bounded RAM, exact search. Full load for small indexes, chunked for large.
- **float16 storage, float32 compute**: Vectors stored as `np.float16` (half memory, half disk). Upcast to `float32` for BLAS-accelerated dot products at search time.
- **Batch embedding**: Chunks sent to embedder in batches, not one at a time.
- **Incremental indexing**: Only re-process changed files. Content-addressed chunk IDs mean unchanged chunks keep their vectors.
- **Frozen dataclasses with slots**: Minimal memory overhead per object, no `__dict__`.
- **msgpack over JSON**: For large serialized structures (BM25 index, graph). JSON where human readability matters.
- **Process pool, not threads**: GIL-free parallelism for CPU-bound parsing. HTTP calls to embedder naturally release GIL but we're multiprocessing anyway.

## Configuration

```json
{
  "embedder": {
    "endpoint": "http://localhost:9876",
    "auth_key": "dorje_...",
    "model": "jina-embeddings-v4",
    "dimension": 2048,
    "batch_size": 64
  },
  "llm": {
    "endpoint": "http://localhost:11434/v1",
    "model": "llama3",
    "auth_key": null
  },
  "index": {
    "path": ".dorje"
  },
  "chunking": {
    "max_tokens": 8192,
    "min_tokens_per_chunk": 128,
    "max_paragraphs_per_chunk": 10,
    "stride_tokens": 256
  },
  "search": {
    "slab_size": null,
    "top_k": 20
  },
  "concurrency": {
    "workers": null
  }
}
```

`workers: null` means auto-detect: `max(cpu_count() - 2, 1) * 2`.

## Dependencies

```
numpy           # Vectors, similarity
tiktoken        # Token counting
tree-sitter     # AST parsing
tree-sitter-python, tree-sitter-javascript, tree-sitter-java, tree-sitter-c, tree-sitter-go
rank-bm25       # BM25 search
openai          # LLM client (OpenAI-compatible)
msgpack         # Fast serialization for index files
```
