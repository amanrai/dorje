from pathlib import Path

from dorje.handles import HandleStore


def test_derivative_handles_are_deterministic_from_content_provenance_and_recipe(tmp_path: Path) -> None:
    store = HandleStore(tmp_path / "handles")

    first = store.put(
        "hello",
        content_type="text/plain",
        metadata={"derived_from": "hf_source", "converter": "demo"},
        derivative_type="conversion",
    )
    second = store.put(
        "hello",
        content_type="text/plain",
        metadata={"converter": "demo", "derived_from": "hf_source"},
        derivative_type="conversion",
    )
    different_recipe = store.put(
        "hello",
        content_type="text/plain",
        metadata={"derived_from": "hf_source", "converter": "other"},
        derivative_type="conversion",
    )

    assert first.handle == second.handle
    assert first.handle != different_recipe.handle


def test_file_ref_handles_are_content_hash_based(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("same", encoding="utf-8")
    copy = tmp_path / "copy.txt"
    copy.write_text("same", encoding="utf-8")
    store = HandleStore(tmp_path / "handles")

    first = store.put_file_ref(path, "text/plain")
    second = store.put_file_ref(copy, "text/plain")

    assert first.handle == second.handle


def test_collection_handles_are_deterministic_from_members_and_recipe(tmp_path: Path) -> None:
    store = HandleStore(tmp_path / "handles")
    members = [{"handle": "h_a"}, {"handle": "h_b"}]

    first = store.put_collection(members, metadata={"filter": {"media_type": "text/html"}}, derivative_type="filtered_collection")
    second = store.put_collection(members, metadata={"filter": {"media_type": "text/html"}}, derivative_type="filtered_collection")

    assert first.handle == second.handle
