"""Measure actual normalized island spacing on unchanged audited geometry."""
import gc
import importlib
import json
from pathlib import Path
import numpy as np
import shapely
import trimesh

root = Path(__file__).resolve().parents[1]
module = importlib.import_module('smart_uv.smart_uv')
configs = [('base_m010', False, .01), ('base_m005', False, .005),
           ('orient_m010', True, .01), ('orient_m005', True, .005),
           ('padded_m010', False, .01), ('padded_m005', False, .005)]
out = root/'tmp/pixal-round4-pixel-spacing-20261012.json'
rows = json.loads(out.read_text()) if out.exists() else []
completed = {(row['case'],row['variant']) for row in rows}
for case in ('person', 'robot', 'helmet'):
    model = json.loads((root/f'tmp/pixal-full-round3-sparse-resume-{case}-metrics.json').read_text())[0]['model']
    mesh = trimesh.load(model, force='mesh', process=False)
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int32)
    for label, orientation, margin in configs:
        if (case,label) in completed:
            continue
        source = root/'tmp/pixal-smart-uv-orientation-candidate.py' if orientation else Path(module.__file__)
        if label.startswith('padded'):
            source = root/'tmp/pixal-smart-uv-padding-candidate.py'
        packing_debug = {}
        ns = dict(vars(module), packing_debug=packing_debug)
        code = source.read_text(encoding='utf-8')
        target = 'final_max = max(next_u1, next_v1)'
        assert code.count(target) == 1
        code = code.replace(target,target+'\n    packing_debug["final_span"] = float(final_max)',1)
        exec(compile(code, str(source), 'exec'), ns)
        native_pack = ns['pack_islands']
        stats = {}
        def pack(islands, **kwargs):
            packed = native_pack(islands, **kwargs)
            scale = 1/packing_debug['final_span']
            lower = np.array([uv.min(axis=0) for uv in packed])
            upper = np.array([uv.max(axis=0) for uv in packed])
            boxes = shapely.box(lower[:,0],lower[:,1],upper[:,0],upper[:,1])
            tree = shapely.STRtree(boxes)
            nearby = tree.query(shapely.box(lower[:,0]-8/1024,lower[:,1]-8/1024,
                                           upper[:,0]+8/1024,upper[:,1]+8/1024))
            i,j = nearby[:,nearby[0]<nearby[1]]
            separation = np.maximum(np.maximum(lower[i],lower[j])-np.minimum(upper[i],upper[j]),0)
            distances = np.linalg.norm(separation,axis=1)*1024
            overlap_size = np.minimum(upper[i],upper[j])-np.maximum(lower[i],lower[j])
            overlaps = np.all(overlap_size>1e-12,axis=1)
            stats.update(islands=len(packed), pack_scale=scale,
                         nominal_two_sided_gutter_1024=2*margin*scale*1024,
                         aabb_overlap_pairs=int(overlaps.sum()),
                         nearby_pair_gap_quantiles=np.quantile(distances,[0,.1,.5,.9]).tolist() if len(distances) else None,
                         nearby_pair_count=len(distances),neighbor_query_padding_pixels=8,
                         nearby_pairs_below_two_pixels=int((distances<2).sum()))
            return packed
        ns['pack_islands'] = pack
        nv,nf,uv,vmap = ns['smart_uv_unwrap'](vertices,faces,margin=margin,angle_limit=np.pi/3,area_weight=0)
        assert np.array_equal(nv[nf],vertices[faces])
        tri=uv[nf].astype(np.float64);a,b=tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]
        areas=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5*1024**2
        path=root/f'tmp/pixal-round4-density-{case}-{label}-20261012.npz'
        assert not path.exists()
        np.savez(path,vertices=nv,faces=nf,uv=uv,vmap=vmap)
        row=dict(case=case,variant=label,margin=margin,geometry=model,npz=str(path),
                 ordered_geometry_exact=True,median_uv_pixel_area=float(np.median(areas)),
                 raw_zero_uv_faces=int((areas==0).sum()),**stats)
        rows.append(row);out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
        del ns,nv,nf,uv,vmap;gc.collect()
