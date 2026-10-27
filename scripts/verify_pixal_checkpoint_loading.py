from pathlib import Path
import importlib
import importlib.util
import sys
import types
import torch
import warnings

warnings.filterwarnings('ignore', message='for .*copying from a non-meta parameter')

root=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
plugin=root/'custom_nodes/ComfyUI-Trellis2-GGUF'
sys.path.insert(0,str(root))
package=types.ModuleType('trellis2_gguf')
package.__path__=[str(plugin/'trellis2_gguf')]
sys.modules['trellis2_gguf']=package
models=importlib.import_module('trellis2_gguf.models')
basename=str(root/'models/Pixal3D-GGUF/texture/slat_flow_imgshape2tex_dit_1_3B_1024_bf16')
initializers={name:getattr(torch.nn.init,name) for name in ['normal_','zeros_','xavier_uniform_']}
manager_spec=importlib.util.spec_from_file_location('trellis2_model_manager',plugin/'model_manager.py')
manager=importlib.util.module_from_spec(manager_spec)
sys.modules['trellis2_model_manager']=manager
manager_spec.loader.exec_module(manager)
original_resolver=manager.resolve_local_path
wrong=Path(basename+'_Q8_0.gguf.wrong-architecture-backup-20261008')
if wrong.exists():
    def resolve_wrong(basename,**kwargs):
        config_file,_,_=original_resolver(basename,**kwargs)
        return config_file,str(wrong),True
    manager.resolve_local_path=resolve_wrong
with torch.device('meta'):
    try:
        models.from_pretrained(basename,enable_gguf=True,gguf_quant='Q8_0',isPixal3D=True)
    except RuntimeError as error:
        assert 'required parameters are missing' in str(error), str(error)
        print('Wrong checkpoint rejected:',error,flush=True)
    else:
        raise AssertionError('Wrong Q8 architecture was accepted')
assert all(getattr(torch.nn.init,name) is fn for name,fn in initializers.items())
manager.resolve_local_path=original_resolver
with torch.device('meta'):
    model=models.from_pretrained(basename,enable_gguf=True,gguf_quant='Q4_K_M',isPixal3D=True)
print('Valid Q4 checkpoint accepted:',type(model).__name__,flush=True)
if wrong.exists():
    with torch.device('meta'):
        model=models.from_pretrained(basename,enable_gguf=True,gguf_quant='Q8_0',isPixal3D=True)
    print('Verified Q8 checkpoint accepted:',type(model).__name__,flush=True)
import safetensors.torch
real_load=safetensors.torch.load_file
devices=[]
def track_load(*args,**kwargs):
    devices.append(kwargs.get('device','cpu'))
    return real_load(*args,**kwargs)
safetensors.torch.load_file=track_load
decoder=str(root/'models/Pixal3D-GGUF/decoder/shape_dec_next_dc_f16c32_fp16')
with torch.device('meta'):
    model=models.from_pretrained(decoder,isPixal3D=True)
safetensors.torch.load_file=real_load
assert devices==['cpu'],devices
print('Valid decoder accepted; safetensors read once on CPU.',flush=True)
