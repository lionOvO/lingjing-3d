"""Compare installed sparse projection with the previous dense transfer path."""
import ast
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
import torch
from PIL import Image
import numpy as np

PATH=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
old=ast.parse(PATH.with_name(PATH.name+'.bak-before-sparse-projection-20261010').read_text())
new=ast.parse(PATH.read_text())
def function(tree,name,ns):
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(PATH),'exec'),ns)
    return ns[name]

class Features:
    def __init__(self,res,device,dtype,naf,k):
        self.grid_resolution=res;self.device=device;self.dtype=dtype
        self.patch_number=2;self.model=SimpleNamespace(config=SimpleNamespace(num_register_tokens=4))
        self.use_naf_upsample=naf;self.naf_tile_factor=k;self.naf_target_size=1024
        self.transform=lambda image:image
        self.naf_model=lambda image,features,size:features+2
    def extract_features(self,image):
        return torch.arange(image.shape[0]*9*8,device=self.device,dtype=self.dtype).reshape(image.shape[0],9,8)/19
    def proj_grid(self,features,*args,**kw):
        n=self.grid_resolution**3
        values=torch.arange(n*8,device=self.device,dtype=torch.float32).reshape(1,n,8)%193
        return (values/23+features.float().mean()).to(self.dtype).expand(features.shape[0],-1,-1).clone()
    def _load_naf(self):pass
    def _proj_naf_tiled(self,image,features,*args,**kw):
        return self.proj_grid(features+2)

records=[]
for device in ('cpu','cuda'):
    for dtype in (torch.float32,torch.float16):
        for res in (32,64):
            for naf,k in ((False,4),(True,1),(True,4)):
                image=torch.ones(2,3,4,4,device=device,dtype=dtype)
                # Include edges, reordered coordinates, duplicate coordinates and batch 1.
                coords=torch.tensor([[1,res-1,0,3],[0,0,0,0],[1,res-1,0,3],[0,2,3,4],[1,res-1,res-1,res-1]],device=device)
                model=Features(res,device,dtype,naf,k)
                ns=dict(torch=torch,np=np,Image=Image,self=SimpleNamespace(low_vram=False),grid_res=res,sparse_indices=tuple(coords[:,a].long() for a in range(4)))
                previous=function(old,'optimized_forward_instance',ns)
                candidate=function(new,'project_sparse_features',ns)
                state=torch.get_rng_state().clone();cuda_state=torch.cuda.get_rng_state().clone()
                z,dense=previous(model,image,1,2,1)
                expected=dense.reshape(2,res,res,res,-1)[tuple(coords[:,a].cpu().long() for a in range(4))]
                z_new,sparse=candidate(model,image,1,2,1)
                assert torch.equal(z,z_new) and torch.equal(expected,sparse)
                assert torch.equal(state,torch.get_rng_state()) and torch.equal(cuda_state,torch.cuda.get_rng_state())
                dense_bytes=dense.numel()*dense.element_size()
                sparse_bytes=sparse.numel()*sparse.element_size()
                records.append(dict(device=device,dtype=str(dtype),grid=res,naf=naf,tile_factor=k,dense_bytes=dense_bytes,sparse_bytes=sparse_bytes,exact=True))
                del dense,expected,z,z_new,sparse

class Sparse:
    def __init__(self,feats,coords):self.feats=feats;self.coords=coords
ns=dict(torch=torch,np=np,Image=Image,nn=torch.nn,SparseTensor=Sparse,hide_src_module=contextlib.nullcontext)
get_cond=function(new,'get_proj_cond_shape',ns)
class Owner:
    device='cuda';low_vram=False
    def load_moge_model(self):raise RuntimeError('fixture uses default camera')
owner=Owner()
for res in (16,32,64):
    model=Features(res,'cuda',torch.float32,True,4)
    for coordinates in ([[0,0,0,0],[0,res-1,1,2]],[[0,2,3,4],[0,0,0,0],[0,2,3,4]]):
        coords=torch.tensor(coordinates,device='cuda')
        image=torch.ones(1,3,4,4,device='cuda')
        if res<32:
            model.__class__.__call__=lambda self,image,**kw:(self.extract_features(image)[:,:5],torch.cat([self.proj_grid(image),self.proj_grid(image+2)],dim=-1))
        result=get_cond(owner,model,image,coords)
        assert result['cond']['proj'].feats.shape==(len(coords),16)
        assert torch.equal(result['cond']['proj'].coords,coords)
        assert not hasattr(model,'_monkeypatched_for_cpu')
        assert not torch.count_nonzero(result['neg_cond']['proj'].feats)
        assert model.grid_resolution==res
Path('tmp/pixal-sparse-projection-regression-20261010.json').write_text(json.dumps(records,indent=2))
print('PASS: 24 dense/sparse comparisons exact, RNG unchanged; repeated conditioning calls do not retain model hooks or coordinates.')
