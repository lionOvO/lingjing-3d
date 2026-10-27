"""Prepare a narrow CuMesh temporary-lifetime/batched-index candidate."""
from pathlib import Path
import ast
import hashlib

ROOT=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\cumesh\remeshing.py')
source=path.read_text(encoding='utf-8')
(ROOT/'tmp/pixal-cumesh-remesh-original-20261009.py').write_text(source,encoding='utf-8')
start=source.index('def remesh_narrow_band_dc_quad(')
stop=source.index('def reconstruct_mesh_dc_quad(',start)
body=source[start:stop]
changes={
 '    pbar.close()\n':'    pbar.close()\n    del pts, dist, _\n',
 '    # -------------------------------------------------------------------------\n    # 5. Topology (quads)':
 '    del hashmap_vert, grid_verts, pts_vert, dist_vert, _\n\n    # -------------------------------------------------------------------------\n    # 5. Topology (quads)',
 '    intersected_dir = torch.cat(dir_list, dim=0).int()\n':
 '    intersected_dir = torch.cat(dir_list, dim=0).int()\n    del quad_list, dir_list, hashmap_vox, coords, intersected, nz\n    del c, v_idx, a_idx, neigh, keys, lookup, mask\n',
 '    active[quad_indices.flatten()] = True\n':
 '    for i in range(0, quad_indices.shape[0], chunk_size):\n        active[quad_indices[i:i + chunk_size].flatten()] = True\n',
 '    mesh_vertices = (dual_verts / resolution - 0.5) * scale + center\n':
 '    mesh_vertices = (dual_verts / resolution - 0.5) * scale + center\n    del dual_verts, vert_map, active\n',
 '        intersected_dir = intersected_dir[is_outer]\n':
 '        intersected_dir = intersected_dir[is_outer]\n        del quad_centers, sdf, is_outer\n    del bvh\n',
 '    used_verts[quad_indices.flatten()] = True\n':
 '    for i in range(0, quad_indices.shape[0], chunk_size):\n        used_verts[quad_indices[i:i + chunk_size].flatten()] = True\n',
 '        quad_indices[i:end] = new_vert_idx[quad_indices[i:end]]        \n':
 '        quad_indices[i:end] = new_vert_idx[quad_indices[i:end]]\n    del used_verts, new_vert_idx\n',
}
for before,after in changes.items():
 assert body.count(before)==1,before
 body=body.replace(before,after,1)
candidate=source[:start]+body+source[stop:]
ast.parse(candidate)
(ROOT/'tmp/pixal-cumesh-remesh-memory-candidate-20261009.py').write_text(candidate,encoding='utf-8')
print('Original SHA',hashlib.sha256(path.read_bytes()).hexdigest())
