"""Check actual run-stage unload blocks release owners before the next stage."""
import ast
import gc
from pathlib import Path
from types import SimpleNamespace
import weakref

source=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree=ast.parse(source.read_text(encoding='utf-8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2ImageTo3DPipeline')
run=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run')
class Payload: pass
class Owner:
    keep_models_loaded=False
    def __init__(self):
        self.model=Payload();self.proj=Payload();self.collected=[]
    def unload_sparse_structure_model(self): self.model=None;gc.collect()
    def unload_pixal3d_image_cond_ss(self): self.proj=None;gc.collect()
    def _cleanup_cuda(self): gc.collect();self.collected.append(True)
def execute(block,ns):
    exec(compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),str(source),'exec'),ns)
ss=next(n for n in run.body if isinstance(n,ast.If) and any(isinstance(c,ast.Call) and ast.unparse(c.func)=='self.unload_sparse_structure_model' for c in ast.walk(n)))
for keep in (False,True):
    owner=Owner();owner.keep_models_loaded=keep
    ns=dict(self=owner,ss_model=owner.model,proj_cond_model=owner.proj,ss_attn_mode='proj');ref=weakref.ref(owner.model)
    proj_ref=weakref.ref(owner.proj)
    execute(ss,ns)
    assert (ref() is not None)==keep
    assert (proj_ref() is not None)==keep
early_shape=next(n for n in ast.walk(run) if isinstance(n,ast.If) and ast.unparse(n.test)=='not self.keep_models_loaded' and any(isinstance(c,ast.Expr) and isinstance(c.value,ast.Call) and ast.unparse(c.value.func)=='self.unload_pixal3d_image_cond_shape_512' for c in n.body))
class ShapeOwner:
    def __init__(self,keep): self.keep_models_loaded=keep;self.shape=Payload()
    def unload_pixal3d_image_cond_shape_512(self): self.shape=None;gc.collect()
for keep in (False,True):
    owner=ShapeOwner(keep)
    ns=dict(self=owner,shape_512_model=owner.shape,cond_512=Payload())
    ref=weakref.ref(owner.shape);cond_ref=weakref.ref(ns['cond_512'])
    execute(early_shape,ns)
    assert (ref() is not None)==keep
    assert cond_ref() is not None
parent=next(n for n in ast.walk(run) if isinstance(n,ast.If) and early_shape in n.body)
assert ast.unparse(parent.test)=="pipeline_type != '512'"
cleanup=next(n for n in run.body if isinstance(n,ast.If) and any(isinstance(c,ast.Assign) and isinstance(c.value,ast.Constant) and c.value.value is None and any(isinstance(t,ast.Name) and t.id=='cond_512' for t in c.targets) for c in n.body))
names=('shape_512_model','shape_1024_model','tex_1024_model','proj_cond_model','cond_512','cond_1024')
for keep in (False,True):
    owner=Owner();owner.keep_models_loaded=keep
    ns=dict(self=owner,**{name:Payload() for name in names})
    refs=[weakref.ref(ns[name]) for name in names]
    execute(cleanup,ns)
    assert all((ref() is not None)==keep for ref in refs)
    assert bool(owner.collected)==(not keep)
decode=next(i for i,n in enumerate(run.body) if isinstance(n,ast.If) and any(isinstance(c,ast.Call) and ast.unparse(c.func)=='self.decode_latent' for c in ast.walk(n)))
assert run.body.index(cleanup)<decode
middle=next(n for n in ast.walk(run) if isinstance(n,ast.If) and ast.unparse(n.test)=="ss_attn_mode == 'proj' and self.low_vram")
class CondOwner:
    def __init__(self,low):
        self.low_vram=low
        self.ss=Payload();self.shape512=Payload();self.shape1024=Payload()
    def unload_pixal3d_image_cond_ss(self): self.ss=None
    def unload_pixal3d_image_cond_shape_512(self): self.shape512=None
    def unload_pixal3d_image_cond_shape_1024(self): self.shape1024=None
    def _cleanup_cuda(self): gc.collect()
for low in (False,True):
    for mode in ('proj','cross'):
        owner=CondOwner(low)
        ns=dict(self=owner,ss_attn_mode=mode,proj_cond_model=owner.ss,
                shape_512_model=owner.shape512,shape_1024_model=owner.shape1024)
        refs=[weakref.ref(ns[name]) for name in ('proj_cond_model','shape_512_model','shape_1024_model')]
        execute(middle,ns)
        assert all((ref() is None)==(low and mode=='proj') for ref in refs)
print('PASS: unloaded stage models/features are collectible before texture/decode; keep_models_loaded retains owners.')
