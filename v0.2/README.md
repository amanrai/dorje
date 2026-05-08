# Dorje v0.2

Fresh Python rebuild focused on a local, CPU-performant SQLite core plus an exploratory agent harness.

## Runtime stack

- `uv` project/venv management
- Python 3.12 for broad native-wheel compatibility
- `apsw` for high-control SQLite access
- SQLite FTS5 for text search
- `sqlite-vec` for in-SQLite vector search
- `numpy`/`scipy` for CPU numerical work
- `fastembed`/ONNX Runtime for CPU-friendly local embeddings
- `tree-sitter-*` grammars for parser work
- `orjson`, `msgpack`, `xxhash` for fast serialization/hashing
- `typer`/`rich` for CLI UX
- Prompt-only skills and Python extension tools

## Setup

```bash
cd v0.2
uv sync
cd sidecar/pi && npm install && cd ../..
```

## Validation

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

## Core commands

```bash
uv run dorje version
uv run dorje doctor
```

## Extension/tool commands

```bash
uv run dorje tools list
uv run dorje tools call echo '{"value":"hello"}'
uv run dorje tools call add '{"a":2,"b":5}'
uv run dorje tools call get_from_wikipedia '{"title":"Battle of Cannae"}'
```

Extension discovery order:

```text
./base_extensions
./.dorje/extensions
~/.dorje/extensions
```

## Skill commands

```bash
uv run dorje skills list
uv run dorje skills show summarize_wikipedia_page
```

Skill discovery order:

```text
./base_skills
./.dorje/skills
~/.dorje/skills
```

## LM commands

Echo provider, no external model:

```bash
uv run dorje lm health --provider echo
uv run dorje lm complete "hello" --provider echo
```

Pi provider, using existing Pi auth/model:

```bash
uv run dorje lm health --provider pi
uv run dorje lm complete "Reply with exactly: ok" --provider pi
```

Structured response schemas:

```bash
uv run dorje lm schemas
uv run dorje lm complete \
  "Extract RDF triples from: Hannibal defeated Rome in the Battle of Cannae." \
  --provider pi \
  --schema rdf_extract
```

## Wikipedia fetch script

Standalone script retained for data experiments:

```bash
uv run python scripts/fetch_wikipedia.py "SQLite"
uv run python scripts/fetch_wikipedia.py "Battle of Cannae"
```

Outputs are written to:

```text
wiki_data/
```
