"""Install the tested feature staging patch, keeping exact original sources."""
import ast
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'local-stack.json').read_text(encoding='utf-8'))
plugin = Path(config['comfyui']['root']) / 'custom_nodes/ComfyUI-Trellis2-GGUF/trellis2_gguf'
pipeline = plugin / 'pipelines/trellis2_image_to_3d.py'
projection = plugin / 'trainers/flow_matching/mixins/image_conditioned_proj.py'
helper = plugin / 'utils/host_buffers.py'
patches = []


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f'Unexpected source; expected unique fragment: {old}')
    return source.replace(old, new, 1)


for path in (projection, pipeline):
    original = path.read_text(encoding='utf-8')
    if 'from ..utils.host_buffers import' in original or 'from ....utils.host_buffers import' in original:
        print(f'Already installed: {path.name}')
        continue
    source = original
    if path == projection:
        source = replace_once(source, 'from ....utils import dist_utils',
                              'from ....utils.host_buffers import copy_features_to_cpu\nfrom ....utils import dist_utils')
        source = replace_once(source,
            'global_queries = self.naf_model.query_encoder(encoded_image).cpu()',
            'global_queries = copy_features_to_cpu(self.naf_model.query_encoder(encoded_image))')
    else:
        source = replace_once(source, 'import random\n',
            'import random\nfrom ..utils.host_buffers import copy_features_to_cpu, cat_features_on_cpu\n')
        source = replace_once(source, 'z_proj_lr_cpu = z_proj_lr.cpu()', 'z_proj_lr_cpu = copy_features_to_cpu(z_proj_lr)')
        source = replace_once(source, 'z_proj_hr_cpu = z_proj_hr.cpu()', 'z_proj_hr_cpu = copy_features_to_cpu(z_proj_hr)')
        source = replace_once(source, 'z_proj = torch.cat([z_proj_lr_cpu, z_proj_hr_cpu], dim=-1)',
            'z_proj = cat_features_on_cpu([z_proj_lr_cpu, z_proj_hr_cpu], dim=-1)')
    ast.parse(source)
    patches.append((path, source))

for path, source in patches:
    backup = path.with_name(path.name + '.bak-before-host-buffers-20261022')
    if backup.exists():
        raise RuntimeError(f'Backup exists; inspect before overwriting: {backup}')

helper_source = (ROOT / 'scripts/pixal_host_buffers.py').read_text(encoding='utf-8')
ast.parse(helper_source)
if helper.exists() and helper.read_text(encoding='utf-8') != helper_source:
    raise RuntimeError('Existing host buffer helper differs; refusing to overwrite')
for path, source in patches:
    shutil.copy2(path, path.with_name(path.name + '.bak-before-host-buffers-20261022'))
    path.write_text(source, encoding='utf-8', newline='\n')
    print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())
helper.write_text(helper_source, encoding='utf-8', newline='\n')
print('Installed host_buffers.py; neural feature precision and sampling settings unchanged')
