"""Preserve sampled RGB and serialize glTF's linear COLOR_0 contract."""
import json
from pathlib import Path
import sys
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pixal_neural_color_glb import write_reference

root=Path(__file__).resolve().parents[1]
original=root/'tmp/pixal-round4-neural-color-reference-20261012.json'
rows=json.loads(original.read_text())
assert len(rows)==3
for row in rows:
    data=np.load(root/f"tmp/pixal-neural-vertex-colors-{row['case']}-20261012.npz")
    path=Path(row['model']).with_name(f"PixalNeuralColorReference_{row['case']}_linear_fixedgeometry_20261012.glb")
    linear=write_reference(path,data['vertices'],data['faces'],data['neural_rgb'])
    mesh=trimesh.load(path,force='mesh',process=False)
    assert np.array_equal(mesh.vertices.astype(np.float32)[mesh.faces],data['vertices'][data['faces']])
    row.update(model=str(path),color_encoding='Float32 linear COLOR_0, converted from native baked sRGB interpretation',
               superseded_diagnostic=Path(row['model']).name,
               correction='Initial uint8 RGB reference is retained but not used for appearance comparisons; it did not apply glTF linear vertex-color encoding.')
out=root/'tmp/pixal-round4-neural-color-reference-linear-20261012.json'
assert not out.exists()
out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
print('PASS three ordered geometries and serialized float32 linear colors')
