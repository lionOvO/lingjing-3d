"""Check temporary prediction serialization without modifying mesh tensors."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pixal_snapshot',ROOT/'scripts/comfy_pixal_validation_snapshot.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for device in ('cpu','cuda'):
 path=ROOT/f'tmp/pixal-snapshot-fixture-{device}-{uuid.uuid4().hex}.npz'
 module.PATHS={'person':path}
 mesh=SimpleNamespace(vertices=torch.arange(9,dtype=torch.float32,device=device).reshape(3,3),
                      faces=torch.tensor([[0,1,2]],dtype=torch.int32,device=device),
                      coords=torch.arange(12,dtype=torch.int32,device=device).reshape(3,4)[:,1:],
                      attrs=torch.arange(18,dtype=torch.float32,device=device).reshape(3,6),
                      voxel_size=.001,voxel_shape=[1024]*3,layout={'base_color':slice(0,3),'metallic':slice(3,4)},coordinate_system='y_up')
 before={name:getattr(mesh,name).clone() for name in ('vertices','faces','coords','attrs')}
 result=module.PixalValidationSnapshot().save(mesh,'person')
 assert result[0] is mesh
 data=np.load(path);meta=json.loads(path.with_suffix('.json').read_text())
 for name,tensor in before.items():
  assert torch.equal(tensor,getattr(mesh,name))
  assert np.array_equal(data[name],tensor.cpu().numpy())
  assert hashlib.sha256(memoryview(data[name]).cast('B')).hexdigest()==meta[name]['sha256']
 try:module.PixalValidationSnapshot().save(mesh,'person')
 except FileExistsError:pass
 else:raise AssertionError('Must preserve an existing prediction')
 try:module.PixalValidationSnapshot().save(mesh,'../../unexpected')
 except KeyError:pass
 else:raise AssertionError('Unknown paths must not be accepted')
print('PASS CPU/CUDA tensor values and identity, strided coords, byte hashes and path/overwrite protection')
