from dorje_lm.ResponseSchemas import get_response_schema, list_response_schemas


def test_response_schema_registry() -> None:
    names = list_response_schemas()

    assert "rdf_extract" in names
    assert "search_plan" in names
    assert get_response_schema("search_plan").model_json_schema()["type"] == "object"
    assert get_response_schema("rdf_extract").model_json_schema()["type"] == "object"
