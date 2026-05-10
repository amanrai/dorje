from dorje.handles import HandleAxes, HandleContract, default_axes_for_derivative, file_ref_axes


def test_handle_contract_matches_empty_axes_as_any() -> None:
    axes = HandleAxes(kind="derivative", media_type="text/markdown", role="artifact", index_state="indexable")

    assert HandleContract().matches(axes)


def test_handle_contract_matches_declared_axes() -> None:
    axes = file_ref_axes("application/pdf")
    contract = HandleContract(kinds=("file_ref",), media_types=("application/pdf",), roles=("source",), index_states=("raw",))

    assert contract.matches(axes)


def test_default_axes_for_derivative_text_are_indexable_artifacts() -> None:
    axes = default_axes_for_derivative("text/html")

    assert axes.kind == "derivative"
    assert axes.role == "artifact"
    assert axes.index_state == "indexable"


def test_default_axes_for_binary_derivative_content_are_raw() -> None:
    axes = default_axes_for_derivative("application/pdf")

    assert axes.kind == "derivative"
    assert axes.index_state == "raw"
