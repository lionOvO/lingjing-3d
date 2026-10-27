"""Make a non-destructive, lower-poly GLB for texture A/B testing."""

import argparse
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh


def main(source: Path, output: Path, target_faces: int) -> None:
    mesh = trimesh.load(source, force="mesh", process=False)
    input_faces = len(mesh.faces)
    if target_faces >= input_faces:
        raise ValueError("Target must be smaller than the original face count")
    working = pymeshlab.MeshSet()
    working.add_mesh(pymeshlab.Mesh(
        vertex_matrix=np.asarray(mesh.vertices),
        face_matrix=np.asarray(mesh.faces),
    ))
    working.meshing_remove_duplicate_faces()
    working.meshing_remove_null_faces()
    working.meshing_remove_unreferenced_vertices()
    working.meshing_decimation_quadric_edge_collapse(
        targetfacenum=target_faces,
        preservetopology=False,
        optimalplacement=False,
        preservenormal=True,
        preserveboundary=True,
    )
    reduced = working.current_mesh()
    result = trimesh.Trimesh(
        vertices=reduced.vertex_matrix(),
        faces=reduced.face_matrix(),
        process=False,
    )
    if len(result.faces) > target_faces * 1.1:
        raise RuntimeError(f"Decimator stopped early at {len(result.faces)} faces")
    original_bounds = mesh.bounds
    if not np.allclose(result.bounds, original_bounds, atol=0.02):
        raise RuntimeError(f"Bounds changed too much: {original_bounds} -> {result.bounds}")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.export(output)
    print(f"{source}: {input_faces} faces -> {output}: {len(result.faces)} faces")
    print(f"Original bounds: {mesh.bounds}; simplified bounds: {result.bounds}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--faces", type=int, default=150000)
    args = parser.parse_args()
    main(args.source, args.output, args.faces)
