# Dorje v0.2

Fresh Python rebuild focused on a local, CPU-performant SQLite core.

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

## Commands

```bash
uv sync
uv run dorje doctor
```
