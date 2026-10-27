from unittest.mock import MagicMock, patch

from app.milvus_schema import VECTOR_INDEX_PARAMS, build_collection_schemas, ensure_collections


def test_ensure_collections_creates_missing_indexes_and_loads_collections():
    collection_schemas = build_collection_schemas()
    schemas = {
        "new_collection": collection_schemas["character_style_collection"],
        "existing_collection": collection_schemas["generation_params_collection"],
    }
    new_collection = MagicMock()
    existing_collection = MagicMock()

    with patch("app.milvus_schema.build_collection_schemas", return_value=schemas), \
         patch("pymilvus.connections.connect"), \
         patch("pymilvus.utility.has_collection", side_effect=[False, True]), \
         patch("pymilvus.Collection", side_effect=[new_collection, existing_collection]) as collection:
        new_collection.has_index.return_value = False
        existing_collection.has_index.return_value = False
        ensure_collections()

    assert collection.call_args_list[0].kwargs == {"name": "new_collection", "schema": schemas["new_collection"]}
    assert collection.call_args_list[1].kwargs == {"name": "existing_collection"}
    new_collection.create_index.assert_called_once_with(
        field_name="style_embedding", index_params=VECTOR_INDEX_PARAMS
    )
    existing_collection.create_index.assert_called_once_with(
        field_name="param_embedding", index_params=VECTOR_INDEX_PARAMS
    )
    new_collection.load.assert_called_once_with()
    existing_collection.load.assert_called_once_with()


def test_ensure_collections_reuses_existing_indexes():
    schema = build_collection_schemas()["material_reference_collection"]
    existing_collection = MagicMock()
    existing_collection.has_index.return_value = True

    with patch("app.milvus_schema.build_collection_schemas", return_value={"existing_collection": schema}), \
         patch("pymilvus.connections.connect"), \
         patch("pymilvus.utility.has_collection", return_value=True), \
         patch("pymilvus.Collection", return_value=existing_collection):
        ensure_collections()

    existing_collection.create_index.assert_not_called()
    existing_collection.load.assert_called_once_with()
