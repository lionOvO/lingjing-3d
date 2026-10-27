"""Compare tiled extraction against full native extraction across tile boundaries."""
import ast
import argparse
import copy
from pathlib import Path

import numpy as np
import torch
import o_voxel.convert.flexible_dual_grid as implementation

SOURCE = Path(implementation.__file__)
parser = argparse.ArgumentParser()
parser.add_argument('--baseline', type=Path, default=SOURCE)
args = parser.parse_args()
tree = ast.parse(args.baseline.read_text(encoding='utf-8'))
method = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'tiled_flexible_dual_grid_to_mesh')
method.decorator_list = []


class CoreOnly(ast.NodeTransformer):
    def visit_Assign(self, node):
        if any(isinstance(target, ast.Name) and target.id == 't_inter' for target in node.targets):
            return ast.parse('t_inter = intersected_flag[mask].contiguous() & torch.all((t_coords >= lower) & (t_coords < upper), dim=1)[:, None]').body[0]
        return node

    def visit_Try(self, node):
        if any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'flexible_dual_grid_to_mesh' for call in ast.walk(node)):
            return self.visit_body(node.body)
        return self.generic_visit(node)

    def visit_body(self, body):
        return [self.visit(statement) for statement in body]


def compile_method(candidate):
    namespace = vars(implementation).copy()
    exec(compile(ast.fix_missing_locations(ast.Module(body=[candidate], type_ignores=[])), str(SOURCE), 'exec'), namespace)
    return namespace['tiled_flexible_dual_grid_to_mesh'], namespace


original, original_ns = compile_method(copy.deepcopy(method))
candidate, candidate_ns = compile_method(CoreOnly().visit(copy.deepcopy(method)))
if args.baseline != SOURCE:
    installed = ast.parse(SOURCE.read_text(encoding='utf-8'))
    installed_method = next(n for n in installed.body if isinstance(n, ast.FunctionDef) and n.name == method.name)
    installed_method.decorator_list = []
    candidate, candidate_ns = compile_method(installed_method)


def triangles(mesh):
    vertices, faces = [tensor.cpu().numpy() for tensor in mesh]
    triangle = vertices[faces]
    # Preserve oriented cyclic order; select the lexicographically smallest cyclic rotation.
    rows = [triangle[:, [i, (i+1)%3, (i+2)%3]].reshape(-1, 9) for i in range(3)]
    stack = np.stack(rows, axis=1)
    order = np.lexsort(stack[..., ::-1].transpose(2, 0, 1), axis=-1)[:, 0]
    canonical = stack[np.arange(len(stack)), order]
    return np.unique(canonical, axis=0), len(canonical)


with torch.no_grad():
    size = 18
    axis = torch.arange(size, dtype=torch.int32, device='cuda')
    coords = torch.stack(torch.meshgrid(axis, axis, axis, indexing='ij'), dim=-1).reshape(-1, 3).contiguous()
    dual = torch.full(coords.shape, .5, dtype=torch.float32, device='cuda')
    weights = torch.ones(len(coords), 1, device='cuda')
    for direction in range(3):
        flags = torch.zeros_like(coords, dtype=torch.bool)
        flags[:, direction] = coords[:, direction] == 8
        kwargs = dict(coords=coords, dual_vertices=dual, intersected_flag=flags, split_weight=weights,
                      aabb=[[-.5]*3, [.5]*3], grid_size=size, train=False)
        full, full_count = triangles(implementation.flexible_dual_grid_to_mesh(**kwargs))
        old, old_count = triangles(original(**kwargs, tile_size=8))
        fixed, fixed_count = triangles(candidate(**kwargs, tile_size=8))
        np.testing.assert_array_equal(full, fixed)
        assert fixed_count == full_count
        np.testing.assert_array_equal(full, old)
        assert old_count > full_count
        print(f'axis={direction}: full={full_count}, old_tiled={old_count}, core_only={fixed_count}', flush=True)
    # Irregular, shifted occupancy and nonuniform split weights exercise arbitrary geometry.
    keep = coords.sum(dim=1) % 11 != 0
    shifted = coords[keep] + torch.tensor([3, 5, 7], dtype=coords.dtype, device='cuda')
    torch.manual_seed(23)
    dual = torch.rand(shifted.shape, device='cuda')
    weights = torch.rand(len(shifted), 1, device='cuda') + .1
    flags = (shifted % 5 == 0)
    kwargs = dict(coords=shifted.contiguous(), dual_vertices=dual, intersected_flag=flags, split_weight=weights,
                  aabb=[[-.5]*3, [.5]*3], grid_size=32, train=False)
    full, full_count = triangles(implementation.flexible_dual_grid_to_mesh(**kwargs))
    fixed, fixed_count = triangles(candidate(**kwargs, tile_size=8))
    np.testing.assert_array_equal(full, fixed)
    assert fixed_count == full_count
    print(f'irregular shifted field: full={full_count}, core_only={fixed_count}', flush=True)
    # A native tile failure must fail the whole operation, instead of exporting a partial mesh.
    def fail(*args, **kwargs):
        raise RuntimeError('native tile failure')
    candidate_ns['flexible_dual_grid_to_mesh'] = fail
    try:
        candidate(**kwargs, tile_size=8)
    except RuntimeError as error:
        assert str(error) == 'native tile failure'
    else:
        raise AssertionError('Failed tile was silently discarded')
print('PASS: all three axes match full native geometry and winding; overlap emits no duplicate faces; native failures propagate.')
