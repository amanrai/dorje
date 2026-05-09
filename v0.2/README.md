# Dorje v0.2

> **DISCLAIMER: This is not for normal use. It has the capability to ruin your system. You own the code if you use this.**

Dorje v0.2 is an exploratory, agent-driven harness. It is intentionally being built to give a language model broad control over skills, tools, code execution, and local project behavior. That is powerful and dangerous.

## Safety / Risk Model

Dorje v0.2 should be treated as **unsafe local automation**.

The agent can already:

- call local Python extension tools
- fetch external content
- store local handles under `.dorje/`
- invoke a Pi-backed model runtime
- route through prompt-only skills
- execute lifecycle hook scripts
- inspect tool outputs and decide what to call next

The project direction explicitly includes letting the agent write and run code. Once enabled, that means Dorje may be able to:

- overwrite files
- delete files
- corrupt repositories
- leak local data through network calls or model prompts
- execute expensive or long-running computations
- create broken or malicious extensions
- modify its own behavior
- consume API/subscription quota unexpectedly
- generate code you do not understand
- persist data in `.dorje/` or other writable paths

### This is not a security sandbox

Any local `run_python`-style tool in v0.2 should be considered **trusted execution with your user permissions**. Timeouts, output limits, subprocesses, prompts, or tool descriptions are accident guards, not security boundaries.

A real production security boundary must live outside the agent, for example:

- container or VM isolation
- no shell access
- fixed Python/uv environment
- no package installation
- explicit read/write mounts
- disabled or controlled network
- CPU/memory/time limits
- separate credentials and secrets policy

The agent itself must not be trusted to enforce policy. The environment must enforce policy.

## What v0.2 Is For

v0.2 is for exploring whether a small set of broad primitives can support a useful agent harness:

- prompt-only skills for behavior
- Python extension tools for capability
- typed content handles for avoiding token waste
- Pi-backed native tool-calling runtime
- lifecycle hooks for observability
- local SQLite/search/KB experiments

v0.2 prioritizes functionality and exploration over safe defaults or polished software engineering. Extraction/packaging/strict hardening is a later `v0.3` concern.

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
uv run dorje -q "Tell me about the battle of cannae from wikipedia"
uv run dorje --logresults -q "Tell me about sqlite from wikipedia"
```

## Extension/tool commands

```bash
uv run dorje tools list
uv run dorje tools call echo '{"value":"hello"}'
uv run dorje tools call add '{"a":2,"b":5}'
uv run dorje tools call get_from_wikipedia '{"title":"Battle of Cannae"}'
uv run dorje tools call store_handle '{"content":"# Hello","content_type":"text/markdown","label":"demo"}'
uv run dorje tools call read_handle_into_context '{"handle":"h_..."}'
uv run dorje tools call chunk_md '{"markdown":"# Title\n\nFirst paragraph.","max_chars":1000}'
uv run dorje tools call chunk_md_handle '{"handle":"h_...","max_chars":2000}'
```

Extension discovery order:

```text
bundled Dorje extensions from the installed distribution
./.dorje/extensions
~/.dorje/extensions
```

## Skill commands

```bash
uv run dorje skills list
uv run dorje skills show fetch_wikipedia_page
uv run dorje skills show summarize_wikipedia_page
```

Skill discovery order:

```text
bundled Dorje skills from the installed distribution
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
