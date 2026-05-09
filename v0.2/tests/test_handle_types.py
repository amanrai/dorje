from dorje.handles import HandleAxes, HandleContract, default_axes_for_stored_content, file_ref_axes


def test_handle_contract_matches_empty_axes_as_any() -> None:
    axes = HandleAxes(kind="stored_content", media_type="text/markdown", role="artifact", index_state="indexable")

    assert HandleContract().matches(axes)


def test_handle_contract_matches_declared_axes() -> None:
    axes = file_ref_axes("application/pdf")
    contract = HandleContract(kinds=("file_ref",), media_types=("application/pdf",), roles=("source",), index_states=("raw",))

    assert contract.matches(axes)


def test_default_axes_for_stored_text_are_indexable_artifacts() -> None:
    axes = default_axes_for_stored_content("text/html")

    assert axes.kind == "stored_content"
    assert axes.role == "artifact"
    assert axes.index_state == "indexable"


def test_default_axes_for_binary_stored_content_are_raw() -> None:
    axes = default_axes_for_stored_content("application/pdf")

    assert axes.kind == "stored_content"
    assert axes.index_state == "raw"
