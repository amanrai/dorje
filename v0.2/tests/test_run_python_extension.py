from pathlib import Path

from dorje.extensions import load_extensions


def test_run_python_executes_code() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = registry.call("run_python", {"code": "print(2 + 3)"})

    assert isinstance(result, dict)
    assert result["exit_code"] == 0
    assert result["stdout"] == "5\n"
    assert result["unsafe"] is True


def test_run_python_receives_input_json() -> None:
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    registry = load_extensions(roots=(root,))

    result = registry.call(
        "run_python",
        {
            "input_json": {"name": "dorje"},
            "code": (
                "import json, os\n"
                "with open(os.environ['DORJE_RUN_PYTHON_INPUT']) as f:\n"
                "    data = json.load(f)\n"
                "print(data['name'])\n"
            ),
        },
    )

    assert isinstance(result, dict)
    assert result["stdout"] == "dorje\n"
