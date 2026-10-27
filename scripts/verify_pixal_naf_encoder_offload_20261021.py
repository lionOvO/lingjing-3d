"""Verify DINO/NAF residency boundaries without altering conditioning values."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import torch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')


def load_function(source, namespace):
    method = next(node for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.FunctionDef) and node.name == 'project_sparse_features')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    return namespace['project_sparse_features']


class Features:
    def __init__(self, res, device, naf, factor):
        self.events = []
        self.device = device
        self.res = res
        self.patch_number = 2
        self.model = SimpleNamespace(config=SimpleNamespace(num_register_tokens=4), cpu=self.offload)
        self.use_naf_upsample = naf
        self.naf_tile_factor = factor
        self.naf_target_size = 1024
        self.transform = lambda image: image
        self.naf_model = self.encode

    def offload(self):
        self.events.append('offload_dino')

    def extract_features(self, image):
        self.events.append('extract_dino')
        return torch.arange(image.shape[0] * 9 * 8, device=self.device,
                            dtype=torch.float32).reshape(image.shape[0], 9, 8) / 19

    def proj_grid(self, features, *args, **kwargs):
        values = torch.arange(self.res ** 3 * 8, device=self.device,
                              dtype=torch.float32).reshape(1, -1, 8) % 193
        return (values / 23 + features.float().mean()).expand(features.shape[0], -1, -1).clone()

    def _load_naf(self):
        self.events.append('load_naf')

    def encode(self, image, features, size):
        self.events.append('encode_naf')
        return features + 2

    def _proj_naf_tiled(self, image, features, *args, **kwargs):
        self.events.append('encode_naf')
        return self.proj_grid(features + 2)


def main():
    source = SOURCE.read_text(encoding='utf-8')
    backup = SOURCE.with_name(SOURCE.name + '.bak-before-naf-encoder-offload-20261021')
    previous = backup.read_text(encoding='utf-8') if backup.exists() else source
    rows = []
    for device in ('cpu', 'cuda'):
        for low in (False, True):
            for naf, factor in ((False, 4), (True, 1), (True, 4)):
                events = []
                owner = SimpleNamespace(low_vram=low, _cleanup_cuda=lambda: events.append('cleanup'))
                res = 32
                coords = torch.tensor([[1, 31, 0, 3], [0, 0, 0, 0], [1, 31, 0, 3], [0, 2, 3, 4]], device=device)
                namespace = dict(torch=torch, np=np, Image=Image, self=owner, grid_res=res,
                                 sparse_indices=tuple(coords[:, axis].long() for axis in range(4)))
                before = load_function(previous, dict(namespace))
                after = load_function(source, dict(namespace))
                image = torch.ones(2, 3, 4, 4, device=device)
                expected = before(Features(res, device, naf, factor), image, 1, 2, 1)
                features = Features(res, device, naf, factor)
                rng = torch.get_rng_state().clone()
                cuda_rng = torch.cuda.get_rng_state().clone()
                actual = after(features, image, 1, 2, 1)
                assert all(torch.equal(a, b) for a, b in zip(actual, expected))
                assert torch.equal(rng, torch.get_rng_state())
                assert torch.equal(cuda_rng, torch.cuda.get_rng_state())
                if low and naf:
                    assert 'offload_dino' in features.events, 'DINO still resident during NAF encoding'
                    assert features.events.index('extract_dino') < features.events.index('load_naf')
                    assert features.events.index('load_naf') < features.events.index('offload_dino')
                    assert features.events.index('offload_dino') < features.events.index('encode_naf')
                else:
                    assert 'offload_dino' not in features.events
                rows.append(dict(device=device, low_vram=low, naf=naf, tile_factor=factor,
                                 conditioning_equal=True, rng_unchanged=True, events=features.events))
    report = dict(completed=True, rows=rows)
    target = ROOT / 'tmp/pixal-naf-encoder-offload-regression-20261021.json'
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'PASS: {len(rows)} CPU/CUDA residency and conditioning comparisons')


if __name__ == '__main__':
    main()
