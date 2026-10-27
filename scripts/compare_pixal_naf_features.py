"""Compare full/tiled NAF on identical real DINO features, using cached local weights."""
from __future__ import annotations
import argparse
import ast
import gc
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import *
import time

import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from transformers import DINOv3ViTModel

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
PLUGIN = COMFY / 'custom_nodes/ComfyUI-Trellis2-GGUF'
CACHE = ROOT / 'tmp/pixal-naf-feature-inputs-round2'
CACHE.mkdir(exist_ok=True)
source_path = PLUGIN / 'trellis2_gguf/trainers/flow_matching/mixins/image_conditioned_proj.py'
source = ast.parse(source_path.read_text(encoding='utf-8'))
class_source = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
methods = [n for n in class_source.body if isinstance(n, ast.FunctionDef) and n.name in ('extract_features', '_proj_naf_tiled')]
definitions = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in (
    'project_points_to_image_batch', 'sample_features', 'ProjGrid')]
ns = dict(globals())
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions + methods, type_ignores=[])), str(source_path), 'exec'), ns)
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['prepare', 'compare'])
parser.add_argument('--images', nargs='+', default=['OIP_clean_1024_rgba.png', 'robot.png', 'Helmet.png'])
args = parser.parse_args()
cameras = {
    'OIP_clean_1024_rgba.png': (.32385555601889754, 3.060760974884033),
    'robot.png': (.6404804609040663, 1.5075860023498535),
    'Helmet.png': (.7826147871057443, 1.2118743658065796),
}
if args.action == 'prepare':
    nodes = ast.parse((PLUGIN / 'nodes.py').read_text(encoding='utf-8'))
    helpers = [n for n in nodes.body if isinstance(n, ast.ClassDef) and n.name in ('ImageUtils', 'Trellis2_GGUFPreProcessImage')]
    exec(compile(ast.fix_missing_locations(ast.Module(body=helpers, type_ignores=[])), str(PLUGIN / 'nodes.py'), 'exec'), ns)
    model = DINOv3ViTModel.from_pretrained(COMFY / 'models/facebook/dinov3-vitl16-pretrain-lvd1689m', local_files_only=True).eval().cuda()
    owner = SimpleNamespace(model=model)
    preprocess = ns['Trellis2_GGUFPreProcessImage']()
    normalize = transforms.Normalize(mean=[.485, .456, .406], std=[.229, .224, .225])
    with torch.no_grad():
        for name in args.images:
            input_image = Image.open(COMFY / 'input' / name).convert('RGBA')
            tensor = ns['ImageUtils'].pil_to_tensor(input_image)
            tensor = preprocess.process(tensor, padding=25, remove_background=True)[0]
            image = ns['ImageUtils'].tensor_to_pil(tensor).resize((512, 512), Image.Resampling.LANCZOS).convert('RGB')
            image = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255
            features = ns['extract_features'](owner, normalize(image))[:, 5:]
            features = features.reshape(1, 32, 32, -1).permute(0, 3, 1, 2).contiguous()
            np.savez(CACHE / f'{Path(name).stem}.npz', image=image.cpu().numpy(), features=features.cpu().numpy())
            print(f'Saved real 512-stage DINO features: {name}', flush=True)
else:
    repository = Path(torch.hub.get_dir()) / 'valeoai_NAF_main'
    assert (Path(torch.hub.get_dir()) / 'checkpoints/naf_release.pth').is_file(), 'Cached NAF weights required'
    # Local package markers already installed by the existing pipeline.
    naf = torch.hub.load(str(repository), 'naf', pretrained=True, device='cuda', source='local', trust_repo=True).eval()
    results = []
    with torch.no_grad():
        for name in args.images:
            data = np.load(CACHE / f'{Path(name).stem}.npz', allow_pickle=False)
            image = torch.from_numpy(data['image']).cuda()
            features = torch.from_numpy(data['features']).cuda()
            projector = ns['ProjGrid'](grid_resolution=32, image_resolution=512).cuda()
            owner = SimpleNamespace(naf_target_size=(512, 512), image_size=512, proj_grid=projector, naf_model=naf)
            angle, distance = [torch.tensor([value], device='cuda') for value in cameras[name]]
            scale = torch.ones(1, device='cuda')
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            full = naf(image, features, (512, 512))
            reference = projector(full, angle, distance, scale, BHWC=False).cpu()
            torch.cuda.synchronize()
            full_seconds = time.perf_counter() - started
            full_peak = torch.cuda.max_memory_allocated()
            del full
            torch.cuda.empty_cache()
            for factor in (2, 4):
                torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                tiled = ns['_proj_naf_tiled'](owner, image, features, angle, distance, scale, None, tile_factor=factor).cpu()
                torch.cuda.synchronize()
                seconds = time.perf_counter() - started
                tiled_peak = torch.cuda.max_memory_allocated()
                difference = tiled-reference
                cosine = F.cosine_similarity(tiled, reference, dim=-1)
                row = dict(image=name, stage='shape_512', tile_factor=factor,
                           full_seconds=full_seconds, tiled_seconds=seconds,
                           full_cuda_allocated_peak=full_peak, tiled_cuda_allocated_peak=tiled_peak,
                           relative_rmse=float(torch.sqrt(difference.square().mean()/reference.square().mean())),
                           cosine_mean=float(cosine.mean()), cosine_p05=float(torch.quantile(cosine, .05)),
                           max_absolute_error=float(difference.abs().max()),
                           source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
                results.append(row)
                (ROOT / 'tmp/pixal-naf-full-tiled-round2-metrics.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print(json.dumps(row), flush=True)
                del tiled, difference, cosine
            del reference, features, image, projector, owner
            gc.collect()
            torch.cuda.empty_cache()
