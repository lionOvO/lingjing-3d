"""Compare real GGUF loader storage, metadata and linear outputs in isolated runs."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
PLUGIN = COMFY / 'custom_nodes/ComfyUI-Trellis2-GGUF'
sys.path[:0] = [str(COMFY), str(PLUGIN)]
import psutil
import torch
from trellis2_gguf import models
from trellis2_gguf.utils import gguf_utils

parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['old', 'new'], required=True)
parser.add_argument('--component', choices=['ss', 'shape512', 'shape1024', 'texture'], required=True)
args = parser.parse_args()
names = dict(ss='ss_flow_img_dit_1_3B_64_bf16', shape512='slat_flow_img2shape_dit_1_3B_512_bf16',
             shape1024='slat_flow_img2shape_dit_1_3B_1024_bf16', texture='slat_flow_imgshape2tex_dit_1_3B_1024_bf16')
loader = models.from_pretrained
if args.variant == 'old':
    namespace = vars(models).copy()
    path = Path(models.__file__).with_name('__init__.py.bak-before-gguf-meta-20261009')
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    loader = namespace['from_pretrained']
torch.manual_seed(731)
started = time.monotonic()
model = loader(names[args.component], enable_gguf=True, gguf_quant='Q4_K_M', isPixal3D=True)
elapsed = time.monotonic() - started
rng_sha256 = hashlib.sha256(torch.get_rng_state().numpy()).hexdigest()
records = {}
for name, tensor in list(model.named_parameters()) + list(model.named_buffers()):
    assert not tensor.is_meta, name
    raw = tensor.detach().as_subclass(torch.Tensor) if type(tensor) is not torch.Tensor else tensor.detach()
    bytes_view = raw.contiguous().view(torch.uint8).numpy()
    records[name] = dict(dtype=str(tensor.dtype), shape=list(tensor.shape),
                         storage_bytes=raw.numel()*raw.element_size(),
                         sha256=hashlib.sha256(bytes_view).hexdigest())
metadata = {name: {key: str(value) for key, value in vars(module).items() if key.startswith('_ggml_')}
            for name, module in model.named_modules() if any(key.startswith('_ggml_') for key in vars(module))}
torch.manual_seed(321)
outputs = {}
with torch.inference_mode():
    layers = [(name, module) for name, module in model.named_modules() if isinstance(module, gguf_utils.GGMLSparseLinear)]
    selected = [layers[0], next(item for item in layers if 'self_attn.to_qkv' in item[0]), layers[-1]]
    for name, module in selected:
        values = torch.randn(3, module.in_features, device='cuda', dtype=torch.bfloat16)
        output = module.forward_ggml_cast_weights(values)
        outputs[name] = output.cpu().float().numpy()
memory = psutil.Process().memory_info()
record = dict(component=args.component, variant=args.variant, seconds=elapsed,
              peak_private_bytes=memory.peak_pagefile, tensors=records, ggml_metadata=metadata,
              cpu_rng_sha256=rng_sha256)
base = ROOT / f'tmp/pixal-gguf-{args.component}-{args.variant}-round2'
base.with_suffix('.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
import numpy as np
np.savez(base.with_suffix('.npz'), **outputs)
print(json.dumps({key: value for key, value in record.items() if key not in {'tensors', 'ggml_metadata'}}), flush=True)
