from pathlib import Path
from typing import Literal

import orjson
import typer
from rich import print
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from dorje import __version__
from dorje.agent_runtime import AgentRequest, AgentRuntimeConfig, create_agent_runtime
from dorje.db import connect, init_schema
from dorje.extensions import load_extensions
from dorje.hints import HintStore
from dorje.skills import load_skills
from dorje.sync import sync_chunks as sync_chunks_action
from dorje.sync import sync_corpus, sync_fts as sync_fts_action, sync_sources as sync_sources_action
from dorje_lm import LMConfig, LMRequest, create_lm_provider
from dorje_lm.ResponseSchemas import get_response_schema, list_response_schemas
from dorje.agent_runtime.types import AgentRuntimeKind

app = typer.Typer(no_args_is_help=True)
lm_app = typer.Typer(no_args_is_help=True)
tools_app = typer.Typer(no_args_is_help=True)
skills_app = typer.Typer(no_args_is_help=True)
hints_app = typer.Typer(no_args_is_help=True)
app.add_typer(lm_app, name="lm")
app.add_typer(tools_app, name="tools")
app.add_typer(skills_app, name="skills")
app.add_typer(hints_app, name="hints")


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    query: str | None = typer.Option(None, "-q", "--query", help="Run an agent query."),
    runtime: str = typer.Option("pi", "--runtime", help="Agent runtime: pi or native."),
    logresults: bool = typer.Option(False, "--logresults", help="Log tool result previews."),
    loglevel: str = typer.Option("all", "--loglevel", help="Agent log level: all, tool_calls, or quiet."),
) -> None:
    """Dorje command line."""
    if ctx.invoked_subcommand is not None:
        return
    if query is None:
        return
    if loglevel not in ("all", "tool_calls", "quiet"):
        raise typer.BadParameter("loglevel must be all, tool_calls, or quiet")
    agent = create_agent_runtime(AgentRuntimeConfig(kind=_agent_runtime(runtime)))
    try:
        response = agent.run(AgentRequest(query=query, context={"log_results": logresults, "log_level": loglevel}))
        print(response.content)
    finally:
        agent.close()


@app.command()
def version() -> None:
    """Print the Dorje version."""
    print(__version__)


@app.command()
def sync(
    path: Path = typer.Argument(Path("."), help="Corpus folder to sync."),
    glob: str = typer.Option("**/*", "--glob", help="Glob of files to include."),
    quiet: bool = typer.Option(False, "--quiet", help="Disable progress UI."),
) -> None:
    """Build/update the corpus source manifest and report changes."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,.0f}/{task.total:,.0f}"),
        TimeElapsedColumn(),
        disable=quiet,
    )
    task_id = progress.add_task("sync scanning", total=1)

    def on_progress(label: str, completed: int, total: int | None) -> None:
        progress.update(task_id, total=total or 1, completed=completed, description=f"sync {label}")

    with progress:
        result = sync_corpus(path, glob=glob, progress_callback=on_progress)
    print(orjson.dumps(result.to_json(), option=orjson.OPT_INDENT_2).decode())


def _run_sync_action(action, path: Path, quiet: bool, **kwargs: object) -> None:
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,.0f}/{task.total:,.0f}"),
        TimeElapsedColumn(),
        disable=quiet,
    )
    task_id = progress.add_task(action.__name__, total=1)

    def on_progress(label: str, completed: int, total: int | None) -> None:
        progress.update(task_id, total=total or 1, completed=completed, description=f"{action.__name__} {label}")

    with progress:
        result = action(path, progress_callback=on_progress, **kwargs)
    print(orjson.dumps(result.to_json(), option=orjson.OPT_INDENT_2).decode())


@app.command("sync_sources")
def sync_sources(
    path: Path = typer.Argument(Path("."), help="Corpus folder to sync."),
    glob: str = typer.Option("**/*", "--glob", help="Glob of files to include."),
    quiet: bool = typer.Option(False, "--quiet", help="Disable progress UI."),
) -> None:
    """Sync file_ref source handles in SQLite against files on disk."""
    _run_sync_action(sync_sources_action, path, quiet, glob=glob)


@app.command("sync_fts")
def sync_fts(
    path: Path = typer.Argument(Path("."), help="Corpus folder to sync."),
    quiet: bool = typer.Option(False, "--quiet", help="Disable progress UI."),
) -> None:
    """Sync full-file text from file_ref handles into SQLite FTS."""
    _run_sync_action(sync_fts_action, path, quiet)


@app.command("sync_chunks")
def sync_chunks(
    path: Path = typer.Argument(Path("."), help="Corpus folder to sync."),
    max_chars: int = typer.Option(2000, "--max-chars", help="Approximate max characters per chunk."),
    quiet: bool = typer.Option(False, "--quiet", help="Disable progress UI."),
) -> None:
    """Sync paragraph chunks from file_ref handles into SQLite FTS."""
    _run_sync_action(sync_chunks_action, path, quiet, max_chars=max_chars)


@app.command()
def doctor() -> None:
    """Verify the CPU-local SQLite/FTS/vector stack."""
    conn = connect()
    init_schema(conn)
    sqlite_row = conn.execute("select sqlite_version()").fetchone()
    vec_row = conn.execute("select vec_version()").fetchone()
    fts_row = conn.execute(
        "select count(*) from pragma_module_list where name = 'fts5'"
    ).fetchone()
    assert sqlite_row is not None
    assert vec_row is not None
    assert fts_row is not None
    sqlite_version = sqlite_row[0]
    vec_version = vec_row[0]
    fts_ok = fts_row[0]

    print("[green]Dorje v0.2 environment OK[/green]")
    print(f"SQLite: {sqlite_version}")
    print(f"FTS5: {'yes' if fts_ok else 'no'}")
    print(f"sqlite-vec: {vec_version}")


@hints_app.command("add")
def hints_add(text: str) -> None:
    """Add a corpus-local hint."""
    hint = HintStore().add(text)
    print(f"Added hint {hint.id}: {hint.text}")


@hints_app.command("list")
def hints_list(include_deleted: bool = typer.Option(False, "--all", help="Include deleted hints.")) -> None:
    """List corpus-local hints."""
    hints = HintStore().list(include_deleted=include_deleted)
    if not hints:
        print("No hints.")
        return
    for hint in hints:
        print(f"{hint.id}\t{hint.status}\t{hint.text}")


@hints_app.command("examine")
def hints_examine() -> None:
    """Show active hints as runtime context."""
    hints = HintStore().active()
    if not hints:
        print("No active hints.")
        return
    for hint in hints:
        print(f"[{hint.id}] {hint.text}")


@hints_app.command("show")
def hints_show(hint_id: int) -> None:
    """Show one hint."""
    try:
        hint = HintStore().get(hint_id, include_deleted=True)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(orjson.dumps(hint.to_json(), option=orjson.OPT_INDENT_2).decode())


@hints_app.command("delete")
def hints_delete(hint_id: int) -> None:
    """Delete a corpus-local hint."""
    try:
        hint = HintStore().delete(hint_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(f"Deleted hint {hint.id}: {hint.text}")


@hints_app.command("clear")
def hints_clear() -> None:
    """Delete all active corpus-local hints."""
    count = HintStore().clear()
    print(f"Deleted {count} active hint(s).")


@skills_app.command("list")
def skills_list() -> None:
    """List discovered prompt-only skills."""
    for skill in load_skills().values():
        print(f"{skill.name}\t{skill.description.strip()}\t{skill.path}")


@skills_app.command("show")
def skills_show(name: str) -> None:
    """Print a skill prompt."""
    skills = load_skills()
    if name not in skills:
        raise typer.BadParameter(f"unknown skill: {name}")
    print(skills[name].text)


@tools_app.command("list")
def tools_list() -> None:
    """List discovered extension tools."""
    registry = load_extensions()
    for spec in registry.list():
        print(f"{spec.name}\t{spec.extension_name}\t{spec.description.strip()}")


@tools_app.command("call")
def tools_call(name: str, args_json: str = typer.Argument("{}")) -> None:
    """Call a discovered extension tool with JSON args."""
    decoded = orjson.loads(args_json)
    if not isinstance(decoded, dict):
        raise typer.BadParameter("args_json must decode to an object")
    registry = load_extensions()
    result = registry.call(name, decoded)
    if isinstance(result, str):
        print(result)
        return
    print(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode())


@lm_app.command("health")
def lm_health(provider: str = "echo", model: str | None = None) -> None:
    """Check an LM provider."""
    lm = create_lm_provider(LMConfig(provider=_lm_provider(provider), model=model))
    try:
        health = lm.health()
        print(health)
    finally:
        lm.close()


@lm_app.command("schemas")
def lm_schemas() -> None:
    """List named structured-output schemas."""
    for name in list_response_schemas():
        print(name)


@lm_app.command("complete")
def lm_complete(
    prompt: str,
    provider: str = "echo",
    model: str | None = None,
    schema: str | None = None,
) -> None:
    """Run one LM completion, optionally validating against a schema."""
    schema_class = get_response_schema(schema) if schema is not None else None
    schema_json = schema_class.model_json_schema() if schema_class is not None else None
    output = "json" if schema_class is not None else "text"
    lm = create_lm_provider(LMConfig(provider=_lm_provider(provider), model=model))
    try:
        response = lm.complete(
            LMRequest(prompt=prompt, model=model, output=output, schema=schema_json)
        )
        if schema_class is None:
            print(response.text)
            return
        parsed = schema_class.model_validate_json(response.text)
        print(orjson.dumps(parsed.model_dump(), option=orjson.OPT_INDENT_2).decode())
    finally:
        lm.close()


def _agent_runtime(value: str) -> AgentRuntimeKind:
    if value == "pi" or value == "native":
        return value
    raise typer.BadParameter("runtime must be pi or native")


def _lm_provider(value: str) -> Literal["echo", "pi"]:
    if value == "echo" or value == "pi":
        return value
    raise typer.BadParameter("provider must be echo or pi")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
