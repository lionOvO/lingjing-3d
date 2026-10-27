"""Bake UV trials on identical audited geometry and saved neural voxel attributes."""
import argparse
import ast
import gc
import hashlib
import importlib
import json
from pathlib import Path
import time
import cv2
import cumesh as CuMesh
from flex_gemm.ops.grid_sample import grid_sample_3d
import numpy as np
import nvdiffrast.torch as dr
from PIL import Image
import torch
import trimesh as Trimesh

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
OUTPUT=PLUGIN.parents[1]/'output'
parser=argparse.ArgumentParser()
parser.add_argument('--cases',nargs='+',choices=['person','robot','helmet'],default=['person','robot','helmet'])
parser.add_argument('--variants',nargs='+',choices=['baseline1024','baseline2048','orientation1024','orientation2048','padding1024','paddinghalf1024','orientationhalf1024'],default=['baseline1024','baseline2048','orientation1024','orientation2048'])
parser.add_argument('--metrics-prefix',default='pixal-full-round3-sparse-resume')
parser.add_argument('--snapshot-prefix',default='pixal-round3-sparse-resume')
parser.add_argument('--date',default='20261011')
parser.add_argument('--result-tag')
args=parser.parse_args()
result_tag=args.result_tag or args.date
source=(PLUGIN/'nodes.py').read_text(encoding='utf-8')
cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='process')
start=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Expr) and 'Sampling attributes...' in ast.unparse(n))
stop=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Delete) and ast.unparse(n)=='del cumesh')
body=[]
for statement in method.body[start:stop]:
    if isinstance(statement,ast.Assign) and ast.unparse(statement).startswith('base_color = cv2.inpaint'):
        body.extend(ast.parse('before_inpaint = base_color.copy()').body)
    body.append(statement)
bake=compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(PLUGIN/'nodes.py'),'exec')

class ProgressBar:
    def update(self,*_):pass

def run(case,variant):
    geometry=json.loads((ROOT/f'tmp/{args.metrics_prefix}-{case}-metrics.json').read_text(encoding='utf-8'))[0]['model']
    final_mesh=Trimesh.load(geometry,force='mesh',process=False)
    gv=np.asarray(final_mesh.vertices,dtype=np.float32)
    gf=np.asarray(final_mesh.faces,dtype=np.int32)
    data=np.load(ROOT/f'tmp/{args.snapshot_prefix}-{case}-prediction-{args.date}.npz',allow_pickle=False)
    vertices=torch.from_numpy(data['vertices'].astype(np.float32,copy=False)).cuda()
    faces=torch.from_numpy(data['faces'].astype(np.int32,copy=False)).cuda()
    bvh=CuMesh.cuBVH(vertices,faces);bvh.vertices=vertices;bvh.faces=faces
    coords=torch.from_numpy(data['coords']).cuda()
    attr_volume=torch.from_numpy(data['attrs']).cuda()
    attr_layout={key:slice(*value) if isinstance(value,list) else value for key,value in json.loads(str(data['layout'].item())).items()}
    voxel_size=torch.as_tensor(data['voxel_size'],dtype=torch.float32,device='cuda').reshape(-1)
    if voxel_size.numel()==1:voxel_size=voxel_size.repeat(3)
    aabb=torch.tensor([[-.5]*3,[.5]*3],dtype=torch.float32,device='cuda')
    grid_size=((aabb[1]-aabb[0])/voxel_size).round().int()
    module=importlib.import_module('smart_uv.smart_uv')
    if variant.startswith('baseline'):
        unwrap=module.smart_uv_unwrap;uv_source=Path(module.__file__)
    elif variant.startswith('orientation'):
        uv_source=ROOT/'tmp/pixal-smart-uv-orientation-candidate.py'
        ns=dict(vars(module));exec(compile(uv_source.read_text(encoding='utf-8'),str(uv_source),'exec'),ns)
        unwrap=ns['smart_uv_unwrap']
    elif variant.startswith('padding'):
        uv_source=ROOT/'tmp/pixal-smart-uv-padding-candidate.py'
        ns=dict(vars(module));exec(compile(uv_source.read_text(encoding='utf-8'),str(uv_source),'exec'),ns)
        unwrap=ns['smart_uv_unwrap']
    else:raise ValueError(variant)
    texture_size=2048 if variant.endswith('2048') else 1024
    torch.cuda.reset_peak_memory_stats();begin=time.monotonic()
    margin=.005 if 'half' in variant else .01
    nv,nf,uv,vmap=unwrap(gv,gf,margin=margin,angle_limit=np.pi/3,area_weight=0)
    assert np.array_equal(nv[nf],gv[gf]),'UV experiment moved or reordered geometry'
    cumesh=CuMesh.CuMesh();cumesh.init(torch.from_numpy(gv).cuda(),torch.from_numpy(gf).cuda())
    cumesh.compute_vertex_normals()
    out_vertices=torch.from_numpy(nv).cuda();out_faces=torch.from_numpy(nf).cuda();out_uvs=torch.from_numpy(uv).cuda()
    out_normals=cumesh.read_vertex_normals()[torch.from_numpy(vmap).long().cuda()]
    pbar=ProgressBar();texture_alpha_mode='OPAQUE';coordinate_system='y_up';double_side_material=False;use_custom_normals=False
    ns=dict(globals(),**locals());exec(bake,ns)
    mesh=ns['textured_mesh']
    filename=f'PixalUVTrial_{case}_{variant}_fixedgeometry_{result_tag}.glb'
    path=OUTPUT/filename
    assert not path.exists(),'Preserve previous trial'
    mesh.export(path,file_type='glb')
    valid=ns['mask'] & (ns['missing_samples']==0)
    assert not np.any(ns['before_inpaint'][valid]!=ns['base_color'][valid]),'Inpainting changed valid neural samples'
    tri=uv[nf].astype(np.float64);edge1,edge2=tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]
    areas=abs(edge1[:,0]*edge2[:,1]-edge1[:,1]*edge2[:,0])*.5*texture_size**2
    row=dict(case=case,variant=variant,model=str(path),geometry=str(geometry),ordered_geometry_exact=True,
             provenance='Fixed audited geometry + saved neural voxel attributes; no neural regeneration',
             uv_source=str(uv_source),uv_source_sha256=hashlib.sha256(uv_source.read_bytes()).hexdigest(),
             vertices=len(nv),faces=len(nf),texture_size=texture_size,margin=margin,zero_uv_faces=int((areas==0).sum()),
             median_uv_pixel_area=float(np.median(areas)),subpixel_triangles=int((areas<1).sum()),
             rasterized_pixels=int(ns['mask'].sum()),missing_voxel_samples=int(ns['missing_samples'].sum()),
             valid_pixels_changed_by_inpaint=0,seconds=time.monotonic()-begin,
             torch_cuda_allocator_peak=torch.cuda.max_memory_allocated())
    print(json.dumps(row),flush=True)
    return row

result_path=ROOT/f'tmp/pixal-fixed-geometry-uv-comparison-{result_tag}.json'
rows=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else []
with torch.no_grad():
    for case in args.cases:
        for variant in args.variants:
            rows.append(run(case,variant))
            gc.collect();torch.cuda.empty_cache()
            result_path.write_text(json.dumps(rows,indent=2),encoding='utf-8')
