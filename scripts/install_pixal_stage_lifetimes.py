"""Release completed cascade stages and defer unused texture conditioners."""
import ast
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'local-stack.json').read_text(encoding='utf-8'))
path = Path(config['comfyui']['root']) / 'custom_nodes/ComfyUI-Trellis2-GGUF/trellis2_gguf/pipelines/trellis2_image_to_3d.py'
source = path.read_text(encoding='utf-8')
if '# Release completed LR owners before HR conditioning.' in source:
    raise SystemExit('Stage lifetime patch already installed')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


tree = ast.parse(source)
method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'sample_shape_slat_cascade')
lines = source.splitlines(keepends=True)
body = ''.join(lines[method.lineno - 1:method.end_lineno])
body = once(body,
    '        if self.low_vram:\n            flow_model_lr.cpu()\n            self._cleanup_cuda()',
    '''        if self.low_vram:
            # Release completed LR owners before HR conditioning.
            if (not self.keep_models_loaded and flow_model_lr is not flow_model
                    and self.models.get('shape_slat_flow_model_512') is flow_model_lr):
                flow_model_lr = None
                self.unload_shape_slat_flow_model_512()
            else:
                flow_model_lr.cpu()
            self._cleanup_cuda()''')
body = once(body,
    '        if self.low_vram:\n            lr_cond = self._cond_cpu(lr_cond)\n            self._cleanup_cuda()',
    '''        # LR conditioning has no consumers after LR sampling; do not copy it to CPU.
        lr_cond = None
        del noise
        if self.low_vram:
            self._cleanup_cuda()''')
body = once(body,
    "        hr_resolution = resolution",
    "        del slat\n        hr_resolution = resolution")
body = once(body,
    '            hr_grid_res = hr_resolution // 16\n            cond = self.get_proj_cond_shape(',
    '            hr_grid_res = hr_resolution // 16\n            cond = None\n            self._cleanup_cuda()\n            cond = self.get_proj_cond_shape(')
source = ''.join(lines[:method.lineno - 1]) + body + ''.join(lines[method.end_lineno:])
run_method = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'run')
run_lines = source.splitlines(keepends=True)
source = ''.join(run_lines[run_method.lineno - 1:run_method.end_lineno])

# The texture conditioner is not used by sparse structure or either shape stage.
source = once(source, '                tex_1024_model = self.load_pixal3d_image_cond_tex_1024()\n', '')
needle = '                self.unload_tex_slat_flow_model_512()\n                self.load_tex_slat_flow_model_1024()'
assert source.count(needle) == 5
source = source.replace(needle,
    "                if ss_attn_mode == 'proj':\n                    tex_1024_model = self.load_pixal3d_image_cond_tex_1024()\n" + needle)

# Transfer the two conditions to the cascade so run() does not keep old owners.
source = once(source,
    "        elif pipeline_type == '1024_cascade':\n            self.load_shape_slat_flow_model_512()",
    "        elif pipeline_type == '1024_cascade':\n"
    "            shape_conditions = [cond_512, cond_1024]\n"
    "            cond_512 = None\n"
    "            if ss_attn_mode == 'proj':\n"
    "                cond_1024 = {}  # Texture projection is rebuilt from the final shape.\n"
    "            self.load_shape_slat_flow_model_512()")
start = source.index("        elif pipeline_type == '1024_cascade':")
end = source.index("        elif pipeline_type == '2048_cascade':", start)
branch = source[start:end]
branch = once(branch, '                cond_512, cond_1024,',
              '                shape_conditions.pop(0), shape_conditions.pop(0),')
source = source[:start] + branch + source[end:]
source = ''.join(run_lines[:run_method.lineno - 1]) + source + ''.join(run_lines[run_method.end_lineno:])
ast.parse(source)
backup = path.with_name(path.name + '.bak-before-stage-lifetimes-20261022')
assert not backup.exists(), str(backup)
shutil.copy2(path, backup)
path.write_text(source, encoding='utf-8', newline='\n')
print('Installed cascade ownership / deferred texture conditioner patch; backup:', backup)
