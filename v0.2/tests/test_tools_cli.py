from typer.testing import CliRunner

from dorje.cli import app


def test_tools_list_shows_produced_derivative_types() -> None:
    result = CliRunner().invoke(app, ["tools", "list"])

    assert result.exit_code == 0
    assert "Requires" in result.output
    assert "Produces" in result.output
    assert "extract_html_to_markdown" in result.output
    assert "file_ref:text/html|application/xhtml+xml" in result.output
    assert "extracted_markdown" in result.output
    assert "collection/table" in result.output
