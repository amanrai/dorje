from typing import Literal

import orjson
import typer
from rich import print

from dorje import __version__
from dorje.db import connect, init_schema
from dorje_lm import LMConfig, LMRequest, create_lm_provider
from dorje_lm.ResponseSchemas import get_response_schema, list_response_schemas

app = typer.Typer(no_args_is_help=True)
lm_app = typer.Typer(no_args_is_help=True)
app.add_typer(lm_app, name="lm")


@app.command()
def version() -> None:
    """Print the Dorje version."""
    print(__version__)


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


def _lm_provider(value: str) -> Literal["echo", "pi"]:
    if value == "echo" or value == "pi":
        return value
    raise typer.BadParameter("provider must be echo or pi")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
