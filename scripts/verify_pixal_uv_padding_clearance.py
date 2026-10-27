"""Test the packer's promised two-sided spacing, not just body overlap."""
import importlib
import json
from pathlib import Path
import numpy as np

root=Path(__file__).resolve().parents[1]
module=importlib.import_module('smart_uv.smart_uv')
source=Path(module.__file__).read_text(encoding='utf-8')
candidate=(root/'tmp/pixal-smart-uv-padding-candidate.py').read_text(encoding='utf-8')
expected=source.replace('if min_dim <= hole_dw and max_dim <= hole_dh:',
                       'if min_dim + 2*margin <= hole_dw and max_dim + 2*margin <= hole_dh:',1)
expected=expected.replace('hole_u0 + (max_dim if hole_rotate else min_dim),\n                 hole_v0 + (min_dim if hole_rotate else max_dim),',
                        'hole_u0 + (max_dim if hole_rotate else min_dim) + 2*margin,\n                 hole_v0 + (min_dim if hole_rotate else max_dim) + 2*margin,',1)
assert candidate==expected, 'Candidate must contain only the hole padding fix'
ns=dict(vars(module));exec(compile(candidate,'<padding-candidate>','exec'),ns)
rows=[]
for seed in range(20):
    rng=np.random.default_rng(seed)
    islands=[np.array([[0,0],[w,0],[w,h],[0,h]]) for w,h in rng.uniform(.001,.25,(160,2))]
    for aspect in (.6,1.,1.6):
        for margin in (0.,.005,.01,.02):
            packed_outputs=[]
            for label,fn in [('installed',module.pack_islands),('candidate',ns['pack_islands'])]:
                packed=fn(islands,margin=margin,target_aspect=aspect);packed_outputs.append(packed)
                scale=np.linalg.norm(np.ptp(packed[0],axis=0))/np.linalg.norm(np.ptp(islands[0],axis=0))
                lower=np.array([p.min(axis=0) for p in packed]);upper=np.array([p.max(axis=0) for p in packed])
                i,j=np.triu_indices(len(packed),1)
                gap=np.linalg.norm(np.maximum(np.maximum(lower[i],lower[j])-np.minimum(upper[i],upper[j]),0),axis=1)
                minimum=float(gap.min());required=2*margin*scale
                violation=minimum<required-1e-12
                if label=='candidate': assert not violation,(seed,aspect,margin,minimum,required)
                rows.append(dict(seed=seed,aspect=aspect,margin=margin,version=label,minimum_gap=minimum,
                                 required_gap=required,spacing_violation=bool(violation)))
            if margin==0:
                assert all(np.array_equal(a,b) for a,b in zip(*packed_outputs))
assert any(r['spacing_violation'] for r in rows if r['version']=='installed')
out=root/'tmp/pixal-round4-padding-clearance-fixtures-20261012.json'
assert not out.exists()
out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
print('PASS 240 rectangle layouts: padded clearance preserved; zero-margin results exact; installed clearance violations reproduced')
