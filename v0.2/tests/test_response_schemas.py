from dorje_lm.ResponseSchemas import get_response_schema, list_response_schemas


def test_response_schema_registry() -> None:
    names = list_response_schemas()

    assert "search_plan" in names
    assert get_response_schema("search_plan").model_json_schema()["type"] == "object"
