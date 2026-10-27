"""Exercise real patched cascade control flow with small CPU tensors."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import torch

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'local-stack.json').read_text(encoding='utf-8'))
path = Path(config['comfyui']['root']) / 'custom_nodes/ComfyUI-Trellis2-GGUF/trellis2_gguf/pipelines/trellis2_image_to_3d.py'


class Sparse:
    def __init__(self, feats, coords):
        self.feats, self.coords = feats, coords
    @property
    def device(self): return self.feats.device
    def __mul__(self, value): return Sparse(self.feats * value, self.coords)
    def __add__(self, value): return Sparse(self.feats + value, self.coords)


class Model:
    in_channels = 2
    low_vram = True
    def __init__(self): self.offloads = 0
    def to(self, device): return self
    def cpu(self): self.offloads += 1; return self
    def upsample(self, slat, **kwargs): return slat.coords


class Pipeline:
    def __init__(self, keep, patched):
        self.low_vram, self.keep_models_loaded = True, keep
        self.device = 'cpu'
        self.shape_slat_sampler_params = {'steps': 16}
        self.shape_slat_normalization = {'std': [1., 1.], 'mean': [0., 0.]}
        self.models = {'shape_slat_flow_model_512': Model()}
        self.patched = patched
        self.cpu_condition_copies = 0
        self.sampler_calls = []
    def _cond_to(self, cond, device): return cond
    def _cond_cpu(self, cond): self.cpu_condition_copies += 1; return cond
    def _cleanup_cuda(self): pass
    def _get_sampler(self, *args): return self
    @property
    def shape_slat_sampler(self): return self
    def sample(self, model, noise, **kwargs):
        self.sampler_calls.append((kwargs['tqdm_desc'], kwargs['steps']))
        return SimpleNamespace(samples=noise)
    def load_shape_slat_decoder(self): self.models['shape_slat_decoder'] = Model()
    def unload_shape_slat_decoder(self): self.models['shape_slat_decoder'] = None
    def unload_shape_slat_flow_model_512(self): self.models['shape_slat_flow_model_512'] = None
    def get_proj_cond_shape(self, *args, **kwargs):
        if self.patched and not self.keep_models_loaded:
            assert self.models['shape_slat_flow_model_512'] is None
        return {'cond': torch.ones(1)}


def extract(source, name):
    node = copy.deepcopy(next(n for n in ast.walk(ast.parse(source))
                              if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    node.returns = None
    for arg in node.args.args + node.args.kwonlyargs:
        arg.annotation = None
    if node.args.kwarg: node.args.kwarg.annotation = None
    scope = {'torch': torch, 'SparseTensor': Sparse}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), scope)
    return scope[name]


def exercise(function, keep, patched):
    pipeline = Pipeline(keep, patched)
    lr = pipeline.models['shape_slat_flow_model_512']
    hr = Model()
    coords = torch.tensor([[0, 1, 2, 3], [0, 4, 5, 6]], dtype=torch.int32)
    torch.manual_seed(991)
    result, resolution = function(pipeline, {'cond': torch.zeros(1)}, {'cond': torch.ones(1)},
        lr, hr, 512, 1024, coords, proj_image_cond_model=object(), proj_images=[None])
    assert pipeline.sampler_calls == [('Sampling shape SLat (LR)', 16), ('Sampling shape SLat (HR)', 16)]
    if patched:
        assert lr.offloads == (1 if keep else 0)
        assert pipeline.cpu_condition_copies == 1  # only HR, no redundant LR copy
    return result.feats, result.coords, resolution


def main():
    torch.set_num_threads(2)
    source = path.read_text(encoding='utf-8')
    original = path.with_name(path.name + '.bak-before-stage-lifetimes-20261022').read_text(encoding='utf-8')
    old = extract(original, 'sample_shape_slat_cascade')
    new = extract(source, 'sample_shape_slat_cascade')
    for keep in (False, True):
        expected = exercise(old, keep, False)
        actual = exercise(new, keep, True)
        torch.testing.assert_close(actual[0], expected[0], rtol=0, atol=0)
        assert torch.equal(actual[1], expected[1]) and actual[2] == expected[2]
        print(f'keep_models_loaded={keep}: LR released/offloaded correctly; sampling tensors unchanged')
    run = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'run')
    # The first conditioner load must be nested in the texture branch, not shape preparation.
    loads = [n for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'load_pixal3d_image_cond_tex_1024']
    assert len(loads) == 5
    print('PASS')


if __name__ == '__main__': main()
