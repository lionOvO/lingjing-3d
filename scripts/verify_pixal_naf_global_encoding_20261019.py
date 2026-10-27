"""Compare a global-encoding NAF tile candidate against real full-image NAF."""
import argparse
import ast
import gc
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple
import time

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\trainers\flow_matching\mixins\image_conditioned_proj.py')
parser = argparse.ArgumentParser()
parser.add_argument('--size', type=int, default=512)
parser.add_argument('--images', nargs='+', default=['OIP_clean_1024_rgba', 'robot', 'Helmet'])
parser.add_argument('--feature-cache', type=Path, default=ROOT / 'tmp/pixal-naf-feature-inputs-round2')
parser.add_argument('--reserve-mib', type=int, default=0)
parser.add_argument('--chunk-rope', action='store_true')
parser.add_argument('--offload-guide', action='store_true')
args = parser.parse_args()
suffix = f'-reserve{args.reserve_mib}' if args.reserve_mib else ''
suffix += '-chunkrope' if args.chunk_rope else ''
suffix += '-offload' if args.offload_guide else ''
report_path = ROOT / f'tmp/pixal-naf-global-encoding-{args.size}{suffix}-20261019.json'
assert not report_path.exists(), report_path
source = SOURCE.read_text(encoding='utf-8')
tree = ast.parse(source)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_proj_naf_tiled')
original = ast.get_source_segment(source, method)
candidate = original.replace('        for ti in range(K):', '''        encoded_image = self.naf_model.image_encoder(image_for_naf, output_size=self.naf_target_size)
        global_queries = self.naf_model.query_encoder(encoded_image)
        global_keys = self.naf_model.key_encoder(encoded_image, lr_features_bchw)

        for ti in range(K):''')
candidate = candidate.replace('''                tile_hr = self.naf_model(
                    image_tile, feature_tile, (tile_out_h, tile_out_w)
                )''', '''                tile_hr = self.naf_model.upsampler(
                    global_queries[:, :, out_lo_y:out_hi_y, out_lo_x:out_hi_x].contiguous(),
                    global_keys[:, :, cell_lo_y:cell_hi_y, cell_lo_x:cell_hi_x].contiguous(),
                    feature_tile,
                )''')
assert candidate != original and 'global_queries[:, :' in candidate
if args.chunk_rope:
    candidate = candidate.replace('''        encoded_image = self.naf_model.image_encoder(image_for_naf, output_size=self.naf_target_size)''', '''        guide = image_for_naf
        if guide.shape[-2] > 4 * naf_h or guide.shape[-1] > 4 * naf_w:
            guide = F.interpolate(guide, size=(min(guide.shape[-2], 4 * naf_h, 4 * naf_w),
                                               min(guide.shape[-1], 4 * naf_w, 4 * naf_h)),
                                  mode="bilinear", align_corners=False)
        encoded_image = self.naf_model.image_encoder.forward_encoder(guide, self.naf_target_size)
        rope = self.naf_model.image_encoder.rope
        coordinates = rope.create_coordinate(H=naf_h, W=naf_w)
        encoded_view = encoded_image.reshape(B, rope.num_heads, rope.D_head, -1).transpose(-1, -2)
        for start in range(0, naf_h * naf_w, 16384):
            stop = min(start + 16384, naf_h * naf_w)
            encoded_view[:, :, start:stop].copy_(rope.rotate(encoded_view[:, :, start:stop], coordinates[start:stop]))''')
if args.offload_guide:
    assert args.chunk_rope
    candidate = candidate.replace('''        global_queries = self.naf_model.query_encoder(encoded_image)
        global_keys = self.naf_model.key_encoder(encoded_image, lr_features_bchw)''', '''        global_keys = self.naf_model.key_encoder(encoded_image, lr_features_bchw)
        # Call-local CPU storage keeps the whole-image guide out of attention's VRAM peak.
        global_queries = self.naf_model.query_encoder(encoded_image).cpu()
        del encoded_view, encoded_image
''')
    candidate = candidate.replace('global_queries[:, :, out_lo_y:out_hi_y, out_lo_x:out_hi_x].contiguous()',
                                  'global_queries[:, :, out_lo_y:out_hi_y, out_lo_x:out_hi_x].to(device).contiguous()')
candidate_path = ROOT / f'tmp/pixal-naf-global-encoding-candidate{suffix}-20261019.py'
if not candidate_path.exists():
    candidate_path.write_text(candidate, encoding='utf-8')
else:
    assert candidate_path.read_text(encoding='utf-8') == candidate
definitions = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ('project_points_to_image_batch', 'sample_features', 'ProjGrid')]
ns = dict(globals())
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[])), str(SOURCE), 'exec'), ns)
exec(compile(original, str(SOURCE), 'exec'), ns)
baseline = ns['_proj_naf_tiled']
exec(compile(candidate, str(candidate_path), 'exec'), ns)
proposed = ns['_proj_naf_tiled']
cameras = {'OIP_clean_1024_rgba':(.32385555601889754,3.060760974884033), 'robot':(.6404804609040663,1.5075860023498535), 'Helmet':(.7826147871057443,1.2118743658065796)}
naf = torch.hub.load(str(Path(torch.hub.get_dir()) / 'valeoai_NAF_main'), 'naf', pretrained=True, device='cuda', source='local', trust_repo=True).eval()
report = dict(source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), candidate_sha256=hashlib.sha256(candidate.encode()).hexdigest(), size=args.size, rows=[])
report['reserved_mib'] = args.reserve_mib
report['chunk_rope'] = args.chunk_rope
report['offload_guide'] = args.offload_guide
torch.set_num_threads(4)
with torch.inference_mode():
    reserved = torch.zeros(args.reserve_mib * 1024 * 1024, device='cuda', dtype=torch.uint8)
    for name in args.images:
        data = np.load(args.feature_cache / f'{name}.npz', allow_pickle=False)
        image = torch.from_numpy(data['image']).cuda()
        features = torch.from_numpy(data['features']).cuda()
        if args.size != 512:
            image = F.interpolate(image, size=(args.size, args.size), mode='bilinear', align_corners=False)
        projector = ns['ProjGrid'](grid_resolution=args.size // 16, image_resolution=args.size).cuda()
        owner = SimpleNamespace(naf_target_size=(args.size, args.size), image_size=args.size, proj_grid=projector, naf_model=naf)
        angle, distance = [torch.tensor([v], device='cuda') for v in cameras[name]]
        scale = torch.ones(1, device='cuda')
        reference = None
        if args.size == 512:
            full = naf(image, features, (args.size, args.size))
            reference = projector(full, angle, distance, scale, BHWC=False).cpu()
            del full
            torch.cuda.empty_cache()
        variants = [('old_k4', baseline, 4), ('global_k4', proposed, 4)]
        variants.append(('global_k2' if args.size == 512 else 'global_k8', proposed, 2 if args.size == 512 else 8))
        if args.reserve_mib:
            variants = [('global_k4', proposed, 4)]
        for label, fn, factor in variants:
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            result = fn(owner, image, features, angle, distance, scale, None, factor).cpu()
            torch.cuda.synchronize()
            row = dict(image=name, variant=label, peak_cuda_allocated=torch.cuda.max_memory_allocated(), seconds=time.monotonic()-started, finite=bool(torch.isfinite(result).all()))
            if reference is not None:
                error = result-reference
                row.update(relative_rmse=float((error.square().mean()/reference.square().mean()).sqrt()), max_abs=float(error.abs().max()))
            if label == 'global_k4':
                k4 = result
            if label in ('global_k2', 'global_k8'):
                error = result-k4
                row['alternate_vs_k4_relative_rmse'] = float((error.square().mean()/k4.square().mean()).sqrt())
            report['rows'].append(row)
            report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(row), flush=True)
            del result
        del k4, reference, image, features, projector, owner
        gc.collect()
        torch.cuda.empty_cache()
report['completed'] = True
report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
