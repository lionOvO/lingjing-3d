"""Check installed NAF tiling for batch/border handling and bilinear fallback."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple
from unittest.mock import patch

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\trainers\flow_matching\mixins\image_conditioned_proj.py')
TARGET = ROOT / 'tmp/pixal-naf-installed-regression-20261019.json'
assert not TARGET.exists()
source = SOURCE.read_text(encoding='utf-8')
old = SOURCE.with_name(SOURCE.name + '.bak-before-global-naf-20261019').read_text(encoding='utf-8')
ns = dict(globals())
tree = ast.parse(source)
definitions = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ('project_points_to_image_batch', 'sample_features', 'ProjGrid')]
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[])), str(SOURCE), 'exec'), ns)
def extract(text):
    cls = next(n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_proj_naf_tiled')
    exec(compile(ast.get_source_segment(text, fn), str(SOURCE), 'exec'), ns)
    return ns['_proj_naf_tiled']
baseline, installed = extract(old), extract(source)
torch.set_num_threads(4)
torch.manual_seed(24019)
report = dict(source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), rows=[])
cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
loader = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_load_naf')
exec(compile(ast.get_source_segment(source, loader), str(SOURCE), 'exec'), ns)
load_owner = SimpleNamespace(naf_model=None, model=nn.Linear(1, 1), _cached_naf_repo=lambda: 'local-test', _naf_is_bilinear=False)
with patch('torch.hub.load', side_effect=RuntimeError('simulated optional dependency unavailable')):
    ns['_load_naf'](load_owner)
assert load_owner._naf_is_bilinear
load_owner.naf_model = None
with patch('torch.hub.load', return_value=nn.Linear(1, 1)):
    ns['_load_naf'](load_owner)
assert not load_owner._naf_is_bilinear
report['rows'].append(dict(kind='optional_loader_failure_then_reload', state_resets=True))

class BilinearNAF(nn.Module):
    def forward(self, image, features, target_size):
        return F.interpolate(features, size=target_size, mode='bilinear', align_corners=False)

with torch.inference_mode():
    data = np.load(ROOT / 'tmp/pixal-naf-feature-inputs-round2/OIP_clean_1024_rgba.npz', allow_pickle=False)
    image = F.interpolate(torch.from_numpy(data['image']), size=(256, 256), mode='bilinear', align_corners=False).repeat(2, 1, 1, 1).cuda()
    features = F.interpolate(torch.from_numpy(data['features'])[:, :64], size=(16, 16), mode='bilinear', align_corners=False).repeat(2, 1, 1, 1).cuda()
    # Distinct cameras include projections outside the image and cross-tile boundaries.
    angle = torch.tensor([.32, .7], device='cuda')
    distance = torch.tensor([.3, 3.], device='cuda')
    scale = torch.tensor([1., 1.5], device='cuda')
    projector = ns['ProjGrid'](grid_resolution=16, image_resolution=256).cuda()
    owner = SimpleNamespace(naf_target_size=(256, 256), image_size=256, proj_grid=projector, naf_model=BilinearNAF(), _naf_is_bilinear=True)
    for factor in (2, 4):
        before = baseline(owner, image, features, angle, distance, scale, None, factor)
        after = installed(owner, image, features, angle, distance, scale, None, factor)
        assert torch.equal(before, after)
        report['rows'].append(dict(kind='bilinear_vs_previous', batch=2, factor=factor, exact=True))
    naf = torch.hub.load(str(Path(torch.hub.get_dir()) / 'valeoai_NAF_main'), 'naf', pretrained=True, device='cuda', source='local', trust_repo=True).eval()
    owner.naf_model, owner._naf_is_bilinear = naf, False
    reference = projector(naf(image, features, (256, 256)), angle, distance, scale, BHWC=False)
    for factor in (2, 4):
        result = installed(owner, image, features, angle, distance, scale, None, factor)
        relative = float(((result-reference).square().mean()/reference.square().mean()).sqrt())
        assert torch.isfinite(result).all() and relative < 1e-5
        report['rows'].append(dict(kind='native_vs_full', batch=2, factor=factor, relative_rmse=relative))
report['completed'] = True
TARGET.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
