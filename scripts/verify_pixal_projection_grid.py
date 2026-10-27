"""Exercise installed sampler projection preludes with partially occupied grids."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import torch

SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2ImageTo3DPipeline')
methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

def prelude(name):
    method = copy.deepcopy(methods[name])
    method.decorator_list = []
    method.returns = None
    for arg in method.args.args:
        arg.annotation = None
    index = next(i for i, n in enumerate(method.body) if isinstance(n, ast.If) and ast.unparse(n.test) == 'proj_image_cond_model is not None and proj_images is not None')
    method.body = method.body[:index + 1] + [ast.Return(value=ast.Name(id='cond', ctx=ast.Load()))]
    ns = {'torch': torch}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(SOURCE), 'exec'), ns)
    return ns[name]

def project(model, images, coords, grid_resolution_override=None, **kwargs):
    # The real projector's physical coordinate convention. Occupancy cannot resize it.
    return (coords[:, 1:].float() / (grid_resolution_override - 1) - .5, grid_resolution_override)

pipeline = SimpleNamespace(device='cpu', low_vram=False, get_proj_cond_shape=project)
coords = torch.tensor([[0, 10, 11, 12], [0, 20, 21, 22]])
for name in ('sample_shape_slat', 'sample_tex_slat', 'sample_tex_slat_advanced'):
    run = prelude(name)
    for grid in (32, 64, 96):
        model = SimpleNamespace(grid_resolution=64)
        value = coords if name == 'sample_shape_slat' else SimpleNamespace(coords=coords)
        points, actual = run(pipeline, {}, None, value, proj_image_cond_model=model, proj_images=[], proj_grid_resolution=grid)
        assert actual == grid
        torch.testing.assert_close(points, coords[:, 1:].float() / (grid - 1) - .5)
        occupied = torch.cat([coords, torch.tensor([[0, grid - 1, grid - 1, grid - 1]])])
        value = occupied if name == 'sample_shape_slat' else SimpleNamespace(coords=occupied)
        extended, _ = run(pipeline, {}, None, value, proj_image_cond_model=model, proj_images=[], proj_grid_resolution=grid)
        torch.testing.assert_close(points, extended[:2])
    value = coords if name == 'sample_shape_slat' else SimpleNamespace(coords=coords)
    assert run(pipeline, {}, None, value, proj_image_cond_model=model, proj_images=[])[1] == 64
    assert run(pipeline, {'standard': 1}, None, value) == {'standard': 1}

# Execute the cascade's actual projection block at elastic output resolutions.
cascade = methods['sample_shape_slat_cascade']
block = next(n for n in cascade.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'proj_image_cond_model is not None and proj_images is not None')
code = compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(block)], type_ignores=[])), str(SOURCE), 'exec')
for res in (1024, 1408, 1536, 2048):
    ns = dict(self=pipeline, proj_image_cond_model=model, proj_images=[], coords=coords, hr_resolution=res)
    exec(code, ns)
    assert ns['cond'][1] == res // 16
run_method = methods['run']
grid_assignment = next(n for n in ast.walk(run_method) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'coords_grid_res')
assert ast.unparse(grid_assignment.value) == 'sparse_structure_resolution'
calls = [n for n in ast.walk(run_method) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'sample_tex_slat']
assert [ast.unparse(next(k.value for k in c.keywords if k.arg == 'proj_grid_resolution')) for c in sorted(calls, key=lambda c: c.lineno)] == ['sparse_structure_resolution'] * 2 + ['res // 16'] * 4
print('PASS: partially occupied 32/64/96 grids retain physical mapping; cascade uses actual output lattice; standard conditioning and fixed-mesh API retained.')
