from typer.testing import CliRunner

from dorje.cli import app


def test_fts_command_searches_materialized_text(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("alpha beta gamma", encoding="utf-8")
    runner = CliRunner()

    assert runner.invoke(app, ["sync", "sources", str(tmp_path), "--quiet"]).exit_code == 0
    assert runner.invoke(app, ["sync", "extract", str(tmp_path), "--quiet"]).exit_code == 0
    assert runner.invoke(app, ["sync", "materialize", str(tmp_path), "--quiet"]).exit_code == 0
    result = runner.invoke(app, ["fts", "-q", "alpha", str(tmp_path)])

    assert result.exit_code == 0
    assert '"count": 1' in result.output
    assert "alpha" in result.output


def test_sync_chunks_and_fts_are_not_user_facing_commands(tmp_path) -> None:
    runner = CliRunner()

    assert runner.invoke(app, ["sync", "chunks", str(tmp_path), "--quiet"]).exit_code != 0
    assert runner.invoke(app, ["sync", "fts", str(tmp_path), "--quiet"]).exit_code != 0
