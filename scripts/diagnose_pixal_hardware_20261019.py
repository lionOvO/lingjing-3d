"""Bounded local diagnostics; does not modify production code or generate a model."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
PLUGIN = COMFY / 'custom_nodes/ComfyUI-Trellis2-GGUF'
sys.path[:0] = [str(COMFY), str(PLUGIN)]
import numpy as np
import torch
import torch.nn.functional as F
from trellis2_gguf import models
from trellis2_gguf.modules.sparse import SparseTensor
from trellis2_gguf.utils import gguf_utils

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['linear', 'decoder'])
args = parser.parse_args()
output = ROOT / f'tmp/pixal-hardware-{args.mode}-20261019.json'
assert not output.exists(), output
torch.set_num_threads(4)
torch.manual_seed(731)
torch.backends.cuda.matmul.allow_tf32 = False
report = dict(mode=args.mode, torch=torch.__version__, cuda=torch.version.cuda,
              gpu=torch.cuda.get_device_name(), capability=torch.cuda.get_device_capability(),
              total_vram=torch.cuda.get_device_properties(0).total_memory, rows=[],
              scope='Local sampled operations, not end-to-end quality or another GPU comparison')
started = time.monotonic()

def save(row):
    report['rows'].append(row)
    report['seconds'] = time.monotonic() - started
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(row), flush=True)

def difference(a, b):
    a, b = a.float().cpu(), b.float().cpu()
    delta = a - b
    return dict(exact=bool(torch.equal(a, b)), finite=bool(torch.isfinite(a).all() and torch.isfinite(b).all()),
                max_abs=float(delta.abs().max()), relative_rmse=float((delta.square().mean() / b.square().mean().clamp_min(1e-30)).sqrt()))

with torch.inference_mode():
    if args.mode == 'linear':
        names = dict(ss='ss_flow_img_dit_1_3B_64_bf16', shape512='slat_flow_img2shape_dit_1_3B_512_bf16',
                     shape1024='slat_flow_img2shape_dit_1_3B_1024_bf16', texture='slat_flow_imgshape2tex_dit_1_3B_1024_bf16')
        quant_outputs = {}
        for component, name in names.items():
            for quant in ('Q4_K_M', 'Q8_0'):
                model = models.from_pretrained(name, enable_gguf=True, gguf_quant=quant, isPixal3D=True).eval()
                layers = [(n, m) for n, m in model.named_modules() if isinstance(m, gguf_utils.GGMLSparseLinear)]
                selected = [layers[0], next(item for item in layers if 'self_attn.to_qkv' in item[0]), layers[-1]]
                for layer_name, module in selected:
                    generator = torch.Generator().manual_seed(321)
                    x = torch.randn(17, module.in_features, generator=generator)
                    cpu_w, cpu_b = module.cast_bias_weight(x)
                    gpu_w, gpu_b = module.cast_bias_weight(x.cuda())
                    weights = difference(gpu_w, cpu_w)
                    expected = F.linear(x, cpu_w, cpu_b)
                    actual = module.forward_ggml_cast_weights(x.cuda()).cpu()
                    arithmetic = difference(actual, expected)
                    assert weights['finite'] and weights['exact'], (component, quant, layer_name, weights)
                    assert arithmetic['finite'] and arithmetic['relative_rmse'] < 2e-5, arithmetic
                    module.cuda()
                    resident = module.forward_ggml_cast_weights(x.cuda()).cpu()
                    module.cpu()
                    returned = module.forward_ggml_cast_weights(x.cuda()).cpu()
                    offload = difference(resident, returned)
                    assert offload['exact'], offload
                    bf16_x = x.cuda().bfloat16()
                    bf16_actual = module.forward_ggml_cast_weights(bf16_x).float().cpu()
                    precision = difference(bf16_actual, actual)
                    quant_outputs[component, quant, layer_name] = actual
                    save(dict(component=component, quant=quant, layer=layer_name, weight=weights,
                              cpu_gpu_float32=arithmetic, offload_roundtrip=offload, bf16_vs_float32=precision))
                    del cpu_w, cpu_b, gpu_w, gpu_b, expected, actual, resident, returned, bf16_x, bf16_actual
                del model, layers, selected, module
                gc.collect()
                torch.cuda.empty_cache()
            for layer_name in [key[2] for key in quant_outputs if key[:2] == (component, 'Q4_K_M')]:
                save(dict(component=component, kind='quantization_difference_not_quality_score', layer=layer_name,
                          q4_vs_q8=difference(quant_outputs[component, 'Q4_K_M', layer_name], quant_outputs[component, 'Q8_0', layer_name])))
    else:
        model = models.from_pretrained(str(COMFY / 'models/Pixal3D-GGUF/decoder/tex_dec_next_dc_f16c32_fp16'), isPixal3D=True).eval().cuda()
        for extent in ((2, 2, 2), (3, 3, 2)):
            xyz = torch.cartesian_prod(*(torch.arange(n, device='cuda', dtype=torch.int32) for n in extent))
            coords = torch.cat([torch.zeros(len(xyz), 1, device='cuda', dtype=torch.int32), xyz], dim=1)
            feats = torch.randn(len(coords), 32, device='cuda') * .5
            results = []
            for low_vram in (False, True):
                model.low_vram = low_vram
                # This decoder consumes shape-decoder subdivisions, not unguided latents.
                guides = []
                parent = coords.clone()
                child = torch.arange(8, device='cuda', dtype=torch.int32)
                offsets = torch.stack([child // (2 ** axis) % 2 for axis in range(3)], dim=1)
                for stage in range(4):
                    guides.append(SparseTensor(feats=torch.ones(len(parent), 8, device='cuda'), coords=parent))
                    xyz_children = parent[:, None, 1:] * 2 + offsets[None]
                    batches = parent[:, None, :1].expand(-1, 8, -1)
                    parent = torch.cat([batches, xyz_children], dim=-1).reshape(-1, 4).contiguous()
                torch.cuda.reset_peak_memory_stats()
                value = model(SparseTensor(feats=feats.clone(), coords=coords.clone()), guide_subs=guides)
                results.append((value.coords.cpu(), value.feats.cpu()))
                peak = torch.cuda.max_memory_allocated()
                save(dict(kind='decoder_run', extent=extent, low_vram=low_vram, output_rows=len(value.feats),
                          peak_allocated=peak, finite=bool(torch.isfinite(value.feats).all())))
                del value, guides, parent
                torch.cuda.empty_cache()
            assert torch.equal(results[0][0], results[1][0])
            delta = difference(results[0][1], results[1][1])
            save(dict(kind='decoder_comparison', extent=extent, same_coordinates=True, low_vs_normal=delta))
            assert delta['finite'] and delta['relative_rmse'] < .005, delta
            del results, feats, coords
        del model
report['completed'] = True
report['peak_cuda_allocated'] = torch.cuda.max_memory_allocated()
report['seconds'] = time.monotonic() - started
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('COMPLETED', output, flush=True)
