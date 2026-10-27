"""Milvus collection schemas from the project database design."""

from pymilvus import CollectionSchema, DataType, FieldSchema


VECTOR_INDEX_PARAMS = {
    "index_type": "AUTOINDEX",
    "metric_type": "COSINE",
    "params": {},
}


def build_collection_schemas() -> dict[str, CollectionSchema]:
    """Return collection definitions without creating remote collections."""
    return {
        "character_style_collection": CollectionSchema(fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="style_embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
            FieldSchema(name="style_name", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="tags", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="generation_params", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="reference_image_url", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="created_at", dtype=DataType.INT64),
        ], description="Anime character style embeddings"),
        "generation_params_collection": CollectionSchema(fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="param_embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
            FieldSchema(name="object_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="model_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="best_params", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="success_rate", dtype=DataType.FLOAT),
            FieldSchema(name="avg_quality_score", dtype=DataType.FLOAT),
        ], description="3D generation parameter embeddings"),
        "material_reference_collection": CollectionSchema(fields=[
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="material_embedding", dtype=DataType.FLOAT_VECTOR, dim=512),
            FieldSchema(name="material_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="pbr_params", dtype=DataType.VARCHAR, max_length=1000),
            FieldSchema(name="preview_url", dtype=DataType.VARCHAR, max_length=500),
        ], description="PBR material reference embeddings"),
    }


def ensure_collections() -> None:
    """Create, index, and load collections required by the agent retrieval workflow."""
    from pymilvus import Collection, connections, utility
    from .config import settings

    connections.connect(alias="default", host=settings.milvus_host, port=settings.milvus_port)
    for name, schema in build_collection_schemas().items():
        if not utility.has_collection(name):
            collection = Collection(name=name, schema=schema)
        else:
            collection = Collection(name=name)

        vector_field = next(
            field.name for field in schema.fields if field.dtype == DataType.FLOAT_VECTOR
        )
        if not collection.has_index():
            collection.create_index(
                field_name=vector_field,
                index_params=VECTOR_INDEX_PARAMS,
            )
        collection.load()
