import typer
from rich import print

from dorje import __version__
from dorje.db import connect, init_schema

app = typer.Typer(no_args_is_help=True)


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
