"""Reject the missing 512 texture model before image conditioning or inference."""
import ast
from pathlib import Path
from types import SimpleNamespace

source = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree = ast.parse(source.read_text(encoding='utf-8'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2ImageTo3DPipeline')
run = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
assign = next(n for n in run.body if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'pipeline_type')
guard = next(n for n in run.body if isinstance(n, ast.If) and 'tex_slat_flow_model_512' in ast.unparse(n.test))
assert run.body.index(guard) < next(i for i, n in enumerate(run.body) if 'seed_all(seed)' == ast.unparse(n))
block = compile(ast.fix_missing_locations(ast.Module(body=[assign, guard], type_ignores=[])), str(source), 'exec')
for texture in (True, False):
    for mode in ('512', '1024', '1024_cascade', '1536_cascade', None):
        for has_512 in (True, False):
            ns = dict(self=SimpleNamespace(default_pipeline_type='1024_cascade',
                _pretrained_args={'models': {'tex_slat_flow_model_512': 'checkpoint'} if has_512 else {}}),
                pipeline_type=mode, generate_texture_slat=texture)
            expected_error = mode == '512' and texture and not has_512
            try:
                exec(block, ns)
            except ValueError as error:
                assert expected_error and '1024_cascade' in str(error)
            else:
                assert not expected_error
print('PASS: missing 512 texture model rejected before GPU work; 512 geometry-only and configured texture models retained.')
