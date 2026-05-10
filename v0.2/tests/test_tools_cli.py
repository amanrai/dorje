from typer.testing import CliRunner

from dorje.cli import app


def test_tools_listnames_outputs_names_alphabetically() -> None:
    result = CliRunner().invoke(app, ["tools", "listnames"])

    assert result.exit_code == 0
    names = [line.strip() for line in result.output.splitlines() if line.strip()]
    assert names == sorted(names)
    assert "extract_html_to_markdown" in names


def test_tools_list_shows_produced_derivative_types() -> None:
    result = CliRunner().invoke(app, ["tools", "list"])

    assert result.exit_code == 0
    assert "Requires" in result.output
    assert "Produces" in result.output
    assert "extract_html_to_markdown" in result.output
    assert "file_ref:text/html" in result.output
    assert "application/xht" in result.output
    assert "extracted_markdown" in result.output
    assert "collection/table" in result.output
