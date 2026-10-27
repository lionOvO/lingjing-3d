"""Exercise the actual package factory and forward path, not an extracted candidate."""
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
PLUGIN = COMFY / 'custom_nodes/ComfyUI-Trellis2-GGUF'
sys.path.insert(0, str(COMFY))
sys.path.insert(0, str(PLUGIN))
from trellis2_gguf.pipelines.trellis2_image_to_3d import Trellis2ImageTo3DPipeline
from trellis2_gguf.trainers.flow_matching.mixins.image_conditioned_proj import DinoV3ProjFeatureExtractor

target = ROOT / 'tmp/pixal-local-condition-factory-regression-20261019.json'
assert not target.exists()
torch.set_num_threads(4)
pipeline = Trellis2ImageTo3DPipeline.__new__(Trellis2ImageTo3DPipeline)
factory = pipeline._get_build_pixal3d_image_cond_model()
owner = factory(dict(model_name=str(COMFY / 'models/facebook/dinov3-vitl16-pretrain-lvd1689m'), image_size=512, grid_resolution=32,
                     use_naf_upsample=True, naf_target_size=512)).cuda()
assert isinstance(owner, DinoV3ProjFeatureExtractor) and not owner.training
owner.naf_tile_factor = 4
with torch.inference_mode():
    data = np.load(ROOT / 'tmp/pixal-naf-feature-inputs-round2/OIP_clean_1024_rgba.npz', allow_pickle=False)
    image = torch.from_numpy(data['image']).cuda()
    features = torch.from_numpy(data['features']).cuda()
    camera = torch.tensor([.32385555601889754], device='cuda')
    distance = torch.tensor([3.060760974884033], device='cuda')
    scale = torch.ones(1, device='cuda')
    global_features, projected = owner(image, camera, distance, scale)
    assert projected.shape == (1, 32768, 2048) and torch.isfinite(projected).all()
    assert not owner._naf_is_bilinear
    owner.model.cpu()
    torch.cuda.empty_cache()
    full = owner.naf_model(image, features, (512, 512))
    reference = owner.proj_grid(full, camera, distance, scale, BHWC=False)
    error = projected[:, :, 1024:] - reference
    relative = float((error.square().mean()/reference.square().mean()).sqrt())
    assert relative < 1e-5
report = dict(completed=True, constructed_local_type=True, native_naf_used=True,
              projected_shape=list(projected.shape), global_shape=list(global_features.shape),
              high_resolution_relative_rmse=relative,
              pipeline_sha256=hashlib.sha256((PLUGIN / 'trellis2_gguf/pipelines/trellis2_image_to_3d.py').read_bytes()).hexdigest())
target.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
