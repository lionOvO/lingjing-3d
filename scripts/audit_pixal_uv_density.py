"""Measure UV triangle footprint on an already validated GLB."""
import json
from pathlib import Path
import numpy as np
import trimesh
ROOT = Path(__file__).resolve().parents[1]
path = Path(json.loads((ROOT / 'tmp/pixal-full-round2-release-metrics.json').read_text(encoding='utf-8'))[0]['model'])
mesh = trimesh.load(path, force='mesh', process=False)
tri = mesh.visual.uv[mesh.faces]
delta1, delta2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
area = abs(delta1[:, 0]*delta2[:, 1]-delta1[:, 1]*delta2[:, 0])*.5*1024**2
result = dict(model=str(path), faces=len(area), atlas_size=1024,
              uv_triangle_pixel_area_quantiles=np.quantile(area, [0, .1, .5, .9, 1]).tolist(),
              triangles_below_one_pixel=int((area < 1).sum()),
              triangles_below_quarter_pixel=int((area < .25).sum()))
(ROOT / 'tmp/pixal-uv-density-round2-metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
