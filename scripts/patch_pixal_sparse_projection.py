"""Avoid dense CPU projection copies at the sparse conditioning boundary."""
import ast
import hashlib
from pathlib import Path

PATH=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='4d8fd64b9f538c7a8da27a9e95fbfcd78665d4c55e0bea4f32f2cc9dab940383'
source=PATH.read_text(encoding='utf-8')
start=source.index('            # monkeypatch the forward of this specific')
end=source.index('            z_proj_st = SparseTensor',start)
old=source[start:end]
body=old[old.index('                def optimized_forward_instance'):old.index('                import types')]
# Keep the existing feature computation local to this conditioning call.
body='\n'.join(line[4:] if line.startswith('    ') else line for line in body.split('\n'))
body=body.replace('optimized_forward_instance','project_sparse_features')
body=body.replace('                if self_instance.grid_resolution < 32:\n                    return original_forward(self_instance, image, camera_angle_x, distance, mesh_scale, transform_matrix)\n','')
body=body.replace('                import torch\n                import numpy as np\n                from PIL import Image\n','')
needle='                    if self_instance.use_naf_upsample:\n                        self_instance._load_naf()'
assert needle in body
body=body.replace(needle,"                    z_proj_lr = z_proj_lr.reshape(B, grid_res, grid_res, grid_res, -1)[sparse_indices]\n\n"+needle)
needle='                        z_proj_lr_cpu = z_proj_lr.cpu()'
assert needle in body
body=body.replace(needle,'                        z_proj_hr = z_proj_hr.reshape(B, grid_res, grid_res, grid_res, -1)[sparse_indices]\n'+needle)
replacement="""            grid_res = image_cond_model.grid_resolution
            sparse_indices = tuple(coords[:, axis].long().to(device) for axis in range(4))
"""+body+"""
            with hide_src_module():
                if grid_res >= 32:
                    z_global, z_proj_sparse = project_sparse_features(
                        image_cond_model, image, camera_angle_x=cam_angle,
                        distance=dist_tensor, mesh_scale=scale_tensor,
                    )
                    z_proj_sparse = z_proj_sparse.to(device)
                else:
                    z_global, z_proj = image_cond_model(
                        image, camera_angle_x=cam_angle, distance=dist_tensor, mesh_scale=scale_tensor,
                    )
                    indices = tuple(index.to(z_proj.device) for index in sparse_indices)
                    z_proj_sparse = z_proj.reshape(B, grid_res, grid_res, grid_res, -1)[indices].to(device)
                    del z_proj
"""
updated=source[:start]+replacement+source[end:]
updated=updated.replace('            del z_proj_grid, z_proj\n','')
ast.parse(updated)
backup=PATH.with_name(PATH.name+'.bak-before-sparse-projection-20261010')
assert not backup.exists()
backup.write_bytes(PATH.read_bytes())
PATH.write_text(updated,encoding='utf-8')
print(hashlib.sha256(PATH.read_bytes()).hexdigest())
