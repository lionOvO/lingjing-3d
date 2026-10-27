"""Compare native cleanup and MeshLib import/fill on fixed stage geometry."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
import cumesh
from meshlib import mrmeshnumpy, mrmeshpy

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=['03_simplify', '04_holes'], required=True)
args = parser.parse_args()
folder = ROOT / 'tmp/pixal-stages-20261009-round2-remesh'
v = np.load(folder / f'{args.stage}-vertices.npy')
f = np.load(folder / f'{args.stage}-faces.npy')
rows = []

def stats(label, vertices, faces):
    _, inverse = np.unique(vertices, axis=0, return_inverse=True)
    welded = inverse[faces]
    t = vertices[faces].astype(np.float64)
    cross = np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0])
    valid = np.any(cross != 0, axis=1)
    oriented = welded[valid]
    rotation = oriented.argmin(axis=1)
    oriented = np.take_along_axis(oriented, (rotation[:,None]+np.arange(3))%3, axis=1)
    row = dict(label=label, vertices=len(vertices), faces=len(faces),
               zero_area=int(np.count_nonzero(~valid)),
               duplicates_valid=len(faces[valid])-len(np.unique(np.sort(faces[valid],axis=1),axis=0)),
               duplicates_valid_exact_positions=len(faces[valid])-len(np.unique(np.sort(welded[valid],axis=1),axis=0)),
               duplicates_valid_same_winding=len(oriented)-len(np.unique(oriented,axis=0)))
    print(json.dumps(row), flush=True)
    rows.append(row)

stats('input', v, f)
cm = cumesh.CuMesh()
cm.init(torch.from_numpy(v).cuda(), torch.from_numpy(f).cuda())
cm.remove_degenerate_faces()
cm.remove_duplicate_faces()
cm.remove_unreferenced_vertices()
cv, cf = cm.read()
cv, cf = cv.cpu().numpy(), cf.cpu().numpy()
stats('native_cleanup', cv, cf)
if args.stage == '03_simplify':
    mesh = mrmeshnumpy.meshFromFacesVerts(cf, cv)
    stats('meshlib_import', mrmeshnumpy.getNumpyVerts(mesh), mrmeshnumpy.getNumpyFaces(mesh.topology))
    edges = mesh.topology.findHoleRepresentiveEdges()
    print('hole_count', len(edges), flush=True)
    for edge in edges:
        params = mrmeshpy.FillHoleParams()
        params.metric = mrmeshpy.getUniversalMetric(mesh)
        mrmeshpy.fillHole(mesh, edge, params)
    fv, ff = mrmeshnumpy.getNumpyVerts(mesh), mrmeshnumpy.getNumpyFaces(mesh.topology)
    stats('meshlib_fill', fv, ff)
    cm.clear_cache()
    cm.init(torch.from_numpy(fv).float().cuda(), torch.from_numpy(ff).int().cuda())
    cm.remove_degenerate_faces()
    cm.remove_duplicate_faces()
    cm.remove_unreferenced_vertices()
    cv, cf = cm.read()
    stats('filled_native_cleanup', cv.cpu().numpy(), cf.cpu().numpy())
(ROOT / f'tmp/pixal-hole-cleanup-probe-{args.stage}.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
