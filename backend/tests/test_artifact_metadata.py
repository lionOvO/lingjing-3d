import pytest
import trimesh

from app.artifact_metadata import glb_statistics


def test_delivery_statistics_are_read_from_a_real_glb():
    mesh = trimesh.creation.box(extents=(1, 2, 3))
    data = mesh.export(file_type='glb')
    stats = glb_statistics(data)
    assert stats['vertex_count'] == len(mesh.vertices)
    assert stats['face_count'] == len(mesh.faces)
    assert stats['file_size_mb'] == len(data) / (1024 * 1024)
    with pytest.raises(ValueError):
        glb_statistics(data[:-4])
