import json

from app.knowledge_seed import build_milvus_row, load_seed_records


def test_blender_modifier_seed_records_are_structured_and_traceable():
    records = load_seed_records()
    assert len(records) >= 8
    assert all(record["source"].startswith("https://docs.blender.org/") for record in records)
    assert all(record["seed_key"] for record in records)
    assert all(record["best_params"]["modifier_policy"]["rule_id"] == record["seed_key"] for record in records)


def test_blender_mesh_index_expansion_is_present():
    records = {record["seed_key"]: record for record in load_seed_records()}
    expected = {
        "blender.mesh.workflow_modes.v1",
        "blender.mesh.primitive_selection.v1",
        "blender.mesh.remesh_policy.v1",
        "blender.mesh.retopology_pipeline.v1",
        "blender.mesh.mesh_analysis_policy.v1",
        "blender.mesh.cleanup_pipeline.v1",
        "blender.mesh.non_manifold_review.v1",
        "blender.mesh.normal_repair_policy.v1",
        "blender.mesh.shading_edges_policy.v1",
        "blender.mesh.symmetry_policy.v1",
        "blender.mesh.topology_edit_operations.v1",
        "blender.mesh.mesh_edit_tool_settings.v1",
        "blender.mesh.shape_key_edit_policy.v1",
        "blender.mesh.vertex_groups_rigging.v1",
        "blender.mesh.uv_timing_and_maps.v1",
        "blender.mesh.uv_seams_stretch.v1",
        "blender.mesh.uv_layout_and_udims.v1",
        "blender.mesh.geometry_data_policy.v1",
    }
    assert expected.issubset(records)


def test_milvus_rows_match_existing_collection_contract():
    for record in load_seed_records():
        row = build_milvus_row(record)
        assert row
        assert "seed_key=" + record["seed_key"] in json.loads(row["tags"]) if record["collection_name"] == "character_style_collection" else True
        if record["collection_name"] == "generation_params_collection":
            assert len(row["param_embedding"]) == 768
            assert json.loads(row["best_params"])["modifier_policy"]["rule_id"] == record["seed_key"]
