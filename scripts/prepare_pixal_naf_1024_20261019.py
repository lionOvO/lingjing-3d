"""Save actual 1024-stage DINO inputs without changing installed inference code."""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import *

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
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
CACHE = ROOT / 'tmp/pixal-naf-feature-inputs-1024-20261019'
CACHE.mkdir(exist_ok=True)
nodes = ast.parse((PLUGIN / 'nodes.py').read_text(encoding='utf-8'))
helpers = [n for n in nodes.body if isinstance(n, ast.ClassDef) and n.name in ('ImageUtils', 'Trellis2_GGUFPreProcessImage')]
ns = dict(globals())
exec(compile(ast.fix_missing_locations(ast.Module(body=helpers, type_ignores=[])), str(PLUGIN / 'nodes.py'), 'exec'), ns)
tree = ast.parse((PLUGIN / 'trellis2_gguf/trainers/flow_matching/mixins/image_conditioned_proj.py').read_text(encoding='utf-8'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'extract_features')
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(PLUGIN), 'exec'), ns)
model = DINOv3ViTModel.from_pretrained(COMFY / 'models/facebook/dinov3-vitl16-pretrain-lvd1689m', local_files_only=True).eval().cuda()
owner = SimpleNamespace(model=model)
normalize = transforms.Normalize(mean=[.485, .456, .406], std=[.229, .224, .225])
with torch.inference_mode():
    for name in ('OIP_clean_1024_rgba.png', 'robot.png', 'Helmet.png'):
        target = CACHE / (Path(name).stem + '.npz')
        assert not target.exists(), target
        tensor = ns['ImageUtils'].pil_to_tensor(Image.open(COMFY / 'input' / name).convert('RGBA'))
        tensor = ns['Trellis2_GGUFPreProcessImage']().process(tensor, padding=25, remove_background=True)[0]
        image = ns['ImageUtils'].tensor_to_pil(tensor).resize((1024, 1024), Image.Resampling.LANCZOS).convert('RGB')
        image = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255
        features = ns['extract_features'](owner, normalize(image))[:, 5:]
        features = features.reshape(1, 64, 64, -1).permute(0, 3, 1, 2).contiguous()
        np.savez(target, image=image.cpu().numpy(), features=features.cpu().numpy())
        print(json.dumps(dict(image=name, features=list(features.shape), file=str(target))), flush=True)
