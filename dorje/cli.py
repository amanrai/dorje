"""CLI — argparse interface for Dorje."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dorje import __version__


def main() -> None:
    """Main entry point for the Dorje CLI."""
    parser = argparse.ArgumentParser(
        prog="dorje",
        description="Folder-level semantic search",
    )
    parser.add_argument(
        "--version", action="version", version=f"dorje {__version__}"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--generate-config", nargs="?", const=".", default=None,
        metavar="PATH",
        help="Generate default config.json in .dorje/ (fails if config exists)",
    )
    parser.add_argument(
        "--generate-config-force-overwrite", nargs="?", const=".", default=None,
        metavar="PATH",
        help="Generate default config.json, overwriting any existing config",
    )
    parser.add_argument(
        "--to-mermaid", nargs="?", const=".", default=None,
        metavar="PATH",
        help="Output knowledge graph as Mermaid diagram (optional path filter)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # dorje index [path]
    index_parser = subparsers.add_parser("index", help="Build index for a directory")
    index_parser.add_argument(
        "path", nargs="?", default=".",
        help="Directory to index (default: current directory)",
    )

    # dorje cleanup [path]
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove local .dorje index")
    cleanup_parser.add_argument(
        "path", nargs="?", default=".",
        help="Directory to clean up (default: current directory)",
    )

    # dorje update [path]
    update_parser = subparsers.add_parser("update", help="Incrementally update index")
    update_parser.add_argument(
        "path", nargs="?", default=".",
        help="Directory to update (default: current directory)",
    )

    # dorje search "query"
    search_parser = subparsers.add_parser("search", help="Search the index")
    search_parser.add_argument(
        "query", nargs="?", default=None,
        help="Search query (reads from stdin if not provided)",
    )
    search_parser.add_argument(
        "--top-k", type=int, default=None,
        help="Number of results to return",
    )
    search_parser.add_argument(
        "--path", default=".",
        help="Directory to search (default: current directory)",
    )

    # dorje config
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.add_argument(
        "action", nargs="?", default="show",
        choices=["show", "init"],
        help="Config action (show: print config, init: initialize .dorje index at path)",
    )
    config_parser.add_argument(
        "--path", default=".",
        help="Directory with .dorje index",
    )

    # dorje pack
    pack_parser = subparsers.add_parser("pack", help="Manage model packs")
    pack_sub = pack_parser.add_subparsers(dest="pack_action")
    pack_sub.add_parser("list", help="List available model packs")
    pack_set_parser = pack_sub.add_parser("set", help="Set active model pack")
    pack_set_parser.add_argument("pack_name", help="Name of the pack to activate")

    # dorje helpme "question"
    helpme_parser = subparsers.add_parser("helpme", help="Ask a question about the codebase")
    helpme_parser.add_argument(
        "question", nargs="?", default=None,
        help="Question to answer (reads from stdin if not provided)",
    )
    helpme_parser.add_argument(
        "--top-k", type=int, default=10,
        help="Number of context chunks to retrieve (default: 10)",
    )
    helpme_parser.add_argument(
        "--path", default=".",
        help="Directory to search (default: current directory)",
    )

    # Global flags as subparser args
    for sub in [index_parser, update_parser, search_parser]:
        sub.add_argument(
            "--enumerate-to-leaves", action="store_true",
            help="List all leaf indexes in the index tree",
        )
        sub.add_argument(
            "--populate-leaves", action="store_true",
            help="Split index into child .dorje dirs matching tree structure",
        )
        sub.add_argument(
            "--to-mermaid", nargs="?", const=".", default=None,
            help="Output knowledge graph as Mermaid diagram (optional path filter)",
        )
        sub.add_argument(
            "--predict-impact", nargs="?", default=None,
            help="Trace impact of a described change",
        )

    args = parser.parse_args()

    # Handle --generate-config and --generate-config-force-overwrite first
    gen_path = args.generate_config
    gen_force_path = args.generate_config_force_overwrite

    if gen_path is not None or gen_force_path is not None:
        _cmd_generate_config(
            path_str=gen_force_path if gen_force_path is not None else gen_path,  # type: ignore[arg-type]
            force=gen_force_path is not None,
            json_output=args.json_output,
        )
        sys.exit(0)

    # Handle top-level --to-mermaid (standalone, no subcommand needed)
    if args.to_mermaid is not None and args.command is None:
        json_output = args.json_output or not sys.stdout.isatty()
        _cmd_to_mermaid(args, json_output)
        sys.exit(0)

    if args.command is None:
        # Check stdin for piped query
        if not sys.stdin.isatty():
            query = sys.stdin.read().strip()
            if query:
                args.command = "search"
                args.query = query
                args.top_k = None
                args.path = "."
                args.enumerate_to_leaves = False
                args.populate_leaves = False
                args.to_mermaid = None
                args.predict_impact = None
            else:
                parser.print_help()
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(1)

    # Auto-detect JSON output for piped stdout
    json_output = args.json_output or not sys.stdout.isatty()

    if args.command == "index":
        _cmd_index(args, json_output)
    elif args.command == "cleanup":
        _cmd_cleanup(args, json_output)
    elif args.command == "update":
        _cmd_update(args, json_output)
    elif args.command == "search":
        _cmd_search(args, json_output)
    elif args.command == "config":
        _cmd_config(args, json_output)
    elif args.command == "helpme":
        _cmd_helpme(args, json_output)
    elif args.command == "pack":
        _cmd_pack(args, json_output)
    else:
        parser.print_help()
        sys.exit(1)

    # Handle --to-mermaid after command completes (available on index/update/search)
    if getattr(args, "to_mermaid", None) is not None:
        _cmd_to_mermaid(args, json_output)


def _cmd_generate_config(path_str: str, force: bool, json_output: bool) -> None:
    """Handle --generate-config and --generate-config-force-overwrite."""
    from dorje.config import generate_config

    config_file = generate_config(force=force)

    if json_output:
        sys.stdout.write(json.dumps({
            "status": "ok",
            "config_path": str(config_file),
        }) + "\n")
    else:
        sys.stdout.write(f"Config generated at {config_file}\n")


def _resolve_path(path_str: str) -> Path:
    """Resolve a path argument to an absolute path."""
    path = Path(path_str).resolve()
    assert path.is_dir(), f"Not a directory: {path}"
    return path


def _cmd_cleanup(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje cleanup' command — remove local .dorje index."""
    import shutil

    root = _resolve_path(args.path)
    index_path = root / ".dorje"

    if not index_path.exists():
        if json_output:
            sys.stdout.write(json.dumps({
                "status": "noop",
                "path": str(index_path),
                "message": "No index found",
            }) + "\n")
        else:
            sys.stdout.write(f"No index found at {index_path}\n")
        return

    assert index_path.is_dir(), f"Expected directory, got file: {index_path}"

    shutil.rmtree(index_path)

    if json_output:
        sys.stdout.write(json.dumps({
            "status": "ok",
            "path": str(index_path),
        }) + "\n")
    else:
        sys.stdout.write(f"Removed {index_path}\n")


def _cmd_index(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje index' command."""
    from dorje.config import load_config
    from dorje.embedder import Embedder
    from dorje.index import build_index

    root = _resolve_path(args.path)
    index_path = root / ".dorje"
    config = load_config()
    embedder = Embedder(config.embedder)

    store = build_index(root, config, embedder)

    partitions = store.all_partitions()
    total_chunks = sum(len(p.read_chunks()) for p in partitions)

    if json_output:
        result = {
            "status": "ok",
            "path": str(root),
            "partitions": len(partitions),
            "chunks": total_chunks,
        }
        sys.stdout.write(json.dumps(result) + "\n")
    else:
        sys.stdout.write(f"Indexed {root}\n")
        sys.stdout.write(f"  {len(partitions)} partitions, {total_chunks} chunks\n")


def _cmd_update(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje update' command."""
    from dorje.config import load_config
    from dorje.embedder import Embedder
    from dorje.index import update_index

    root = _resolve_path(args.path)
    index_path = root / ".dorje"
    config = load_config()
    embedder = Embedder(config.embedder)

    store = update_index(root, config, embedder)

    partitions = store.all_partitions()
    total_chunks = sum(len(p.read_chunks()) for p in partitions)

    if json_output:
        result = {
            "status": "ok",
            "path": str(root),
            "partitions": len(partitions),
            "chunks": total_chunks,
        }
        sys.stdout.write(json.dumps(result) + "\n")
    else:
        sys.stdout.write(f"Updated {root}\n")
        sys.stdout.write(f"  {len(partitions)} partitions, {total_chunks} chunks\n")


def _cmd_search(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje search' command."""
    from dorje.config import Config, SearchConfig, load_config
    from dorje.embedder import Embedder
    from dorje.llm import LLMClient
    from dorje.search import SearchWeights, search
    from dorje.storage import IndexStore

    query = args.query
    if query is None:
        if not sys.stdin.isatty():
            query = sys.stdin.read().strip()
        if not query:
            sys.stderr.write("Error: no query provided\n")
            sys.exit(2)

    root = _resolve_path(args.path)
    index_path = root / ".dorje"

    if not index_path.exists():
        sys.stderr.write(f"Error: no index found at {index_path}\n")
        sys.stderr.write("Run 'dorje index' first.\n")
        sys.exit(3)

    config = load_config()

    if args.top_k is not None:
        # Override top_k from CLI
        from dorje.config import SearchConfig
        config = Config(
            embedder=config.embedder,
            llm=config.llm,
            chunking=config.chunking,
            search=SearchConfig(slab_size=config.search.slab_size, top_k=args.top_k),
            concurrency=config.concurrency,
        )

    embedder = Embedder(config.embedder)
    store = IndexStore(index_path)
    store.load()

    # Classify query for weights
    llm = LLMClient(config.llm)
    intent = llm.classify_query(query)
    weights = SearchWeights(
        content_vector=intent.content_weight,
        metadata_vector=intent.metadata_weight,
        bm25=intent.bm25_weight,
        graph=intent.graph_weight,
    )

    results = search(query, store, embedder, config, weights)

    if json_output:
        output = {
            "query": query,
            "intent": intent.intent_type,
            "results": [
                {
                    "path": r.chunk.path,
                    "start_line": r.chunk.start_line,
                    "end_line": r.chunk.end_line,
                    "score": round(r.score, 4),
                    "source": r.source,
                    "chunk_type": r.chunk.chunk_type,
                    "name": r.chunk.metadata.name,
                    "content": r.chunk.content[:500],
                }
                for r in results
            ],
        }
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
    else:
        if not results:
            sys.stdout.write("No results found.\n")
            sys.exit(2)

        for i, r in enumerate(results):
            name = r.chunk.metadata.name or r.chunk.chunk_type
            sys.stdout.write(
                f"{i + 1}. {r.chunk.path}:{r.chunk.start_line} "
                f"[{name}] ({r.source}, {r.score:.3f})\n"
            )
            # Show first 3 lines of content
            preview_lines = r.chunk.content.splitlines()[:3]
            for line in preview_lines:
                sys.stdout.write(f"   {line}\n")
            sys.stdout.write("\n")


def _cmd_to_mermaid(args: argparse.Namespace, json_output: bool) -> None:
    """Handle --to-mermaid flag — output knowledge graph as Mermaid diagram."""
    from dorje.mermaid import graph_to_mermaid
    from dorje.storage import IndexStore

    path_str = getattr(args, "path", ".")
    root = _resolve_path(path_str)
    index_path = root / ".dorje"

    assert index_path.exists(), (
        f"No index found at {index_path}. Run 'dorje index' first."
    )

    store = IndexStore(index_path)
    store.load()

    path_filter = args.to_mermaid if args.to_mermaid != "." else None
    mermaid = graph_to_mermaid(store, path_filter=path_filter)

    if json_output:
        sys.stdout.write(json.dumps({"mermaid": mermaid}) + "\n")
    else:
        sys.stdout.write(mermaid + "\n")


def _cmd_helpme(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje helpme' command — RAG over the codebase."""
    from dorje.config import Config, SearchConfig, load_config
    from dorje.embedder import Embedder
    from dorje.llm import LLMClient
    from dorje.search import SearchWeights, search
    from dorje.storage import IndexStore

    question = args.question
    if question is None:
        if not sys.stdin.isatty():
            question = sys.stdin.read().strip()
        if not question:
            sys.stderr.write("Error: no question provided\n")
            sys.exit(2)

    root = _resolve_path(args.path)
    index_path = root / ".dorje"

    assert index_path.exists(), (
        f"No index found at {index_path}. Run 'dorje index' first."
    )

    config = load_config()

    assert config.llm.enabled, (
        "LLM must be enabled for helpme. Set llm.enabled=true in ~/.dorje/config.json"
    )

    # Override top_k for context retrieval
    retrieve_k = args.top_k
    retrieval_config = Config(
        embedder=config.embedder,
        llm=config.llm,
        chunking=config.chunking,
        search=SearchConfig(slab_size=config.search.slab_size, top_k=retrieve_k),
        concurrency=config.concurrency,
    )

    embedder = Embedder(config.embedder)
    store = IndexStore(index_path)
    store.load()

    llm = LLMClient(config.llm)

    # Classify and search
    intent = llm.classify_query(question)
    weights = SearchWeights(
        content_vector=intent.content_weight,
        metadata_vector=intent.metadata_weight,
        bm25=intent.bm25_weight,
        graph=intent.graph_weight,
    )

    results = search(question, store, embedder, retrieval_config, weights)

    if not results:
        sys.stderr.write("No relevant code found in the index.\n")
        sys.exit(2)

    # Build context chunks with location info
    context_chunks: list[str] = []
    for r in results:
        header = f"# {r.chunk.path}:{r.chunk.start_line}"
        if r.chunk.metadata.name:
            header += f" ({r.chunk.metadata.name})"
        context_chunks.append(f"{header}\n{r.chunk.content}")

    # Ask the LLM
    answer = llm.answer_question(question, context_chunks)

    if json_output:
        output = {
            "question": question,
            "answer": answer,
            "sources": [
                {
                    "path": r.chunk.path,
                    "start_line": r.chunk.start_line,
                    "end_line": r.chunk.end_line,
                    "name": r.chunk.metadata.name,
                    "score": round(r.score, 4),
                }
                for r in results
            ],
        }
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
    else:
        sys.stdout.write(answer + "\n\n")
        sys.stdout.write("--- Sources ---\n")
        for i, r in enumerate(results[:5]):
            name = r.chunk.metadata.name or r.chunk.chunk_type
            sys.stdout.write(
                f"  {i + 1}. {r.chunk.path}:{r.chunk.start_line} [{name}]\n"
            )


def _cmd_config(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje config' command."""
    root = _resolve_path(args.path)
    index_path = root / ".dorje"

    if args.action == "init":
        # Initialize a .dorje index directory at this path (e.g., a subfolder).
        # Creates scope.json and partition structure. Does NOT generate config.json —
        # that's --generate-config at the project root.
        from dorje.storage import IndexStore
        store = IndexStore(index_path)
        store.initialize()

        if json_output:
            sys.stdout.write(json.dumps({
                "status": "ok",
                "path": str(index_path),
            }) + "\n")
        else:
            sys.stdout.write(f"Initialized index at {index_path}\n")

    elif args.action == "show":
        config_path = index_path / "config.json"
        assert config_path.exists(), (
            f"No config found at {config_path}. Run 'dorje --generate-config' first."
        )
        sys.stdout.write(config_path.read_text(encoding="utf-8"))


def _cmd_pack(args: argparse.Namespace, json_output: bool) -> None:
    """Handle 'dorje pack' command — list or set model packs."""
    from dorje.config import list_packs, set_pack

    action = args.pack_action

    if action == "list":
        packs = list_packs()
        if json_output:
            sys.stdout.write(json.dumps(packs, indent=2) + "\n")
        else:
            if not packs:
                sys.stdout.write("No packs found. Run 'dorje --generate-config' first.\n")
                return
            for name, pack in sorted(packs.items()):
                assert isinstance(pack, dict), f"pack '{name}' must be a dict"
                embedder = pack.get("embedder", {})
                llm = pack.get("llm", {})
                assert isinstance(embedder, dict), f"pack '{name}' embedder must be a dict"
                assert isinstance(llm, dict), f"pack '{name}' llm must be a dict"
                e_model = embedder.get("model", "—")
                l_model = llm.get("model", "—")
                sys.stdout.write(f"  {name}\n")
                sys.stdout.write(f"    embedder: {e_model}\n")
                sys.stdout.write(f"    llm:      {l_model}\n")

    elif action == "set":
        pack_name = args.pack_name
        set_pack(pack_name)
        if json_output:
            sys.stdout.write(json.dumps({
                "status": "ok",
                "pack": pack_name,
            }) + "\n")
        else:
            sys.stdout.write(f"Active pack set to '{pack_name}'\n")

    else:
        sys.stderr.write("Usage: dorje pack {list|set <name>}\n")
        sys.exit(1)


