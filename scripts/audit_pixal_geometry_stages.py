"""Measure saved geometry without treating UV-split render vertices as physical holes."""
import argparse
import gc
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('folder', type=Path)
args = parser.parse_args()
rows = json.loads((args.folder / 'manifest.json').read_text(encoding='utf-8'))
results = []
for row in rows:
    vertices = np.load(args.folder / f"{row['stage']}-vertices.npy", mmap_mode='r')
    faces = np.load(args.folder / f"{row['stage']}-faces.npy", mmap_mode='r')
    # Exact position welding for topology analysis only; no changes to the generation mesh.
    unique_vertices, inverse = np.unique(vertices, axis=0, return_inverse=True)
    welded = inverse[faces].astype(np.uint32)
    del inverse
    repeated = np.count_nonzero((welded[:, 0] == welded[:, 1]) | (welded[:, 1] == welded[:, 2]) | (welded[:, 0] == welded[:, 2]))
    zero_area = 0
    tiny_area = 0
    head_zero_area = 0
    head_faces = 0
    for start in range(0, len(faces), 200000):
        triangles = np.asarray(vertices[faces[start:start + 200000]], dtype=np.float64)
        area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) * .5
        head = triangles[:, :, 1].mean(axis=1) > .15
        zero_area += np.count_nonzero(area == 0)
        tiny_area += np.count_nonzero(area < 1e-12)
        head_zero_area += np.count_nonzero((area == 0) & head)
        head_faces += np.count_nonzero(head)
    triangles_key = np.sort(welded, axis=1)
    unique_faces = len(np.unique(triangles_key, axis=0))
    del triangles_key
    # uint32 vertex IDs make this a collision-free uint64 undirected edge encoding.
    edges = np.empty(len(welded) * 3, dtype=np.uint64)
    for index, (left, right) in enumerate(((0, 1), (1, 2), (2, 0))):
        lo = np.minimum(welded[:, left], welded[:, right]).astype(np.uint64)
        hi = np.maximum(welded[:, left], welded[:, right]).astype(np.uint64)
        edges[index * len(welded):(index + 1) * len(welded)] = (lo << 32) | hi
    del lo, hi, welded
    edge_keys, counts = np.unique(edges, return_counts=True)
    del edges
    boundary = edge_keys[counts == 1]
    boundary_vertices = np.unique(np.concatenate([(boundary >> 32).astype(np.uint32), boundary.astype(np.uint32)]))
    head_boundary = np.count_nonzero(unique_vertices[boundary_vertices, 1] > .15)
    result = dict(row, exact_welded_vertices=len(unique_vertices), duplicate_faces_ignoring_winding=len(faces)-unique_faces,
                  repeated_position_faces=int(repeated), zero_area_faces=int(zero_area), tiny_area_faces=int(tiny_area),
                  boundary_edges=int(np.count_nonzero(counts == 1)), nonmanifold_edges=int(np.count_nonzero(counts > 2)),
                  head_faces=int(head_faces), head_zero_area_faces=int(head_zero_area), head_boundary_vertices=int(head_boundary),
                  finite_vertices=bool(np.isfinite(vertices).all()))
    results.append(result)
    (args.folder / 'metrics.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)
    del vertices, faces, unique_vertices, edge_keys, counts, boundary, boundary_vertices
    gc.collect()
