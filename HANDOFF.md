# Dorje — Handoff Document

## What Is Dorje

Folder-level semantic search CLI for codebases. Indexes code files into chunks, embeds them, and provides unified search across three modalities: vector similarity, BM25 keyword search, and knowledge graph traversal. Primary consumers are AI agents; humans are secondary.

## Architecture

- **No daemon** — embeddings and LLM served externally via OpenAI-compatible API (vLLM, vllm-mlx, etc.)
- **Distributed index** — every folder can have its own `.dorje/` index with `scope.json` defining what it covers and what it delegates to child indexes
- **Partitioned storage** — chunks grouped by top-level path component, each partition stores vectors, BM25 data, and graph data independently
- **Two vectors per chunk** — content vector (the code itself) + metadata vector (structured AST info rendered as text)
- **float16 storage, float32 compute** — numpy BLAS-accelerated cosine similarity
- **Slab-based vector reads** — configurable memory ceiling for large indexes
- **Config at `~/.dorje/config.json`** — must exist before any command runs, no code-based defaults for environment-specific values

## External Services

Defined in `external.sh`. Currently split across two machines:
- **Embedder**: `nomic-ai/CodeRankEmbed` (768 dim) on Linux box at `192.168.0.123:34567` via vLLM
- **LLM**: `HuggingFaceTB/SmolLM3-3B` on Mac Mini M4 at `192.168.0.140:34568` via vllm-mlx

CodeRankEmbed has a 2048 token context limit. Config `max_tokens` is set to 1024 for safety margin.

## Package Structure

```
dorje/
├── __init__.py          # version
├── __main__.py          # python -m dorje entry point
├── cli.py               # argparse CLI, all command handlers
├── config.py            # dataclass configs, load/save/generate from ~/.dorje/config.json
├── types.py             # Chunk, ChunkMetadata, GraphNode, Triple, SearchResult, ASTContext
├── discovery.py         # file walker respecting .gitignore + .dorjeignore
├── chunker.py           # token-limited chunking with striding (tiktoken cl100k_base)
├── embedder.py          # OpenAI-compatible embedding client with batching
├── storage.py           # IndexStore, PartitionStore, Scope — msgpack + numpy persistence
├── index.py             # build_index(), update_index() — full pipeline orchestrator
├── search.py            # fusion orchestrator — runs all modalities, normalizes, fuses
├── vector_search.py     # brute-force cosine similarity with min-heap top-k
├── bm25_search.py       # BM25 keyword search via rank_bm25
├── graph_search.py      # BFS traversal + semantic node/verb search
├── llm.py               # query classification, diff summarization, RAG answer_question
├── mermaid.py           # knowledge graph → Mermaid diagram
└── parsers/
    ├── __init__.py      # registry with @register decorator, LanguageParser protocol
    ├── python.py        # tree-sitter Python parser (functions, classes, imports, graph)
    └── fallback.py      # paragraph-based chunking for unknown file types
```

## What Works Now

| Command | Status |
|---|---|
| `dorje index [path]` | Works. Discovers, chunks, embeds, stores. |
| `dorje update [path]` | Works. Incremental via SHA-256 file hash comparison. |
| `dorje search "query"` | Works. Full 3-modality fusion with LLM query classification. |
| `dorje cleanup [path]` | Works. Removes local `.dorje/` directory. |
| `dorje helpme "question"` | Works. RAG — retrieves context chunks, sends to LLM. |
| `dorje config show/init` | Works. |
| `dorje --generate-config` | Works. |
| `dorje --to-mermaid [path]` | Works. Standalone or as subcommand flag. |
| `dorje --json` | Works. Auto-detected for piped stdout. |
| Stdin piping | Works. `echo "query" \| dorje` |

## What Is NOT Built

### Parsers (only Python exists)
- **JavaScript/TypeScript** — needs tree-sitter-javascript/typescript
- **Java** — needs tree-sitter-java
- **Go** — needs tree-sitter-go
- **C/C++** — needs tree-sitter-c/cpp

The parser registry (`@register` decorator) is ready. Each parser needs: `parse()`, `extract_ast_context()`, `build_graph()`. See `python.py` for the reference implementation.

### CLI Features (argparse wired, no backend)
- **`--predict-impact "change description"`** — trace impact through dependency graph. The graph data is there; needs BFS from affected nodes, scoring by distance, and output formatting.
- **`--populate-leaves`** — split a parent index into child `.dorje/` dirs matching tree structure. Should be file copy (no re-embedding). Storage layer has `enumerate_leaves()` already.
- **`--enumerate-to-leaves`** — walk full delegation tree and list leaf indexes. `IndexStore.enumerate_leaves()` exists but isn't wired to CLI output.

### Git History Pipeline
- Not started at all. The architecture calls for indexing git log, diffs, blame. Chunk types would be "commit", and metadata would include author, date, files changed. The LLM `summarize_diff()` method exists but nothing calls it.

### Tests
- Zero test files exist. No unit tests, no integration tests.

### Missing Quality-of-Life
- No `--verbose` / `--quiet` flags
- No progress output for `search` or `helpme` (only `index` has a progress bar)
- No result pagination
- `highlights` field on SearchResult is always empty tuple

## Coding Rules

All code follows **NASA Power of 10**:
1. Short functions (under ~60 lines)
2. No recursion (bounded loops with safety limits)
3. Assertions everywhere — validate inputs, check invariants
4. No dynamic allocation after init where avoidable
5. All loops bounded with explicit max iterations

**No hardcoded environment-specific defaults.** Endpoint URLs, model names, IPs are empty strings / 0 in code. User must fill in `~/.dorje/config.json`.

## Key Design Decisions

- **No global index** — every index is local to its folder, delegates to children
- **`scope.json`** per `.dorje/` dir defines `covers` (path prefix) and `delegates` (child index paths)
- **Partition key** = first path component (e.g., `dorje/cli.py` → partition `dorje`)
- **Triple bidirectional flag** — some relationships are symmetric (e.g., "related to")
- **Graph verbs are embedded** — enables semantic verb matching ("depends on" ≈ "uses")
- **Multiprocessing**: `max(cpu_count - 2, 1) * 2` workers for chunking
- **Tiktoken (cl100k_base)** for token counting — not the model's tokenizer, so chunks are cut conservatively

## Config Format

Auth keys live in `~/.dorje/.env` (never in config.json):
```
DORJE_EMBEDDER_AUTH_KEY=sk-...
DORJE_LLM_AUTH_KEY=sk-...
```

Model packs live in `~/.dorje/packs.json` — named presets for provider+model combos. Set active pack via `dorje pack set <name>`.

`~/.dorje/config.json`:
```json
{
  "pack": "openai",
  "embedder": {
    "endpoint": "http://...:34567/v1",
    "model": "nomic-ai/CodeRankEmbed",
    "dimension": 768,
    "batch_size": 64
  },
  "llm": {
    "endpoint": "http://...:34568/v1",
    "model": "HuggingFaceTB/SmolLM3-3B",
    "enabled": true
  },
  "chunking": {
    "max_tokens": 1024,
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

## Dependencies

From `pyproject.toml`: numpy, msgpack, tiktoken, openai, rank-bm25, tree-sitter, tree-sitter-python.

## Entry Points

- `dorje` CLI via `dorje.cli:main`
- `python -m dorje` via `dorje/__main__.py`
