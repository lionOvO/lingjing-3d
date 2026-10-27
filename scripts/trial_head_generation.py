"""One local head reconstruction trial, isolated from saved user tasks."""
import ctypes,json,time,sys
from ctypes import wintypes
from pathlib import Path
import httpx
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/head-reconstruction-20261023';OUT.mkdir(exist_ok=True)
class PI(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache','KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(n,wintypes.DWORD) for n in ('HandleCount','ProcessCount','ThreadCount')]
def memory():
    p=PI(cb=ctypes.sizeof(PI));assert ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.cb)
    return {'headroom_gib':(p.CommitLimit-p.CommitTotal)*p.PageSize/2**30,'available_ram_gib':p.PhysicalAvailable*p.PageSize/2**30}

def main():
    client=httpx.Client(base_url='http://127.0.0.1:8188',trust_env=False,timeout=60)
    q=client.get('/queue').json();assert not q['queue_running'] and not q['queue_pending'],'Engine busy'
    assert memory()['headroom_gib']>6,'Insufficient commit headroom before trial'
    original=Image.open(ROOT/'tmp/face-quality-20261023/original.png').convert('RGBA')
    mask=Image.open(ROOT/'tmp/face-quality-20261023/input.png').getchannel('A')
    # Inverse of the recorded preparation transform, not a new segmentation.
    scale=972.8/1407
    alpha=mask.transform(original.size,Image.Transform.AFFINE,(scale,0,349.52096659559345-287*scale,0,scale,25.6-11*scale),Image.Resampling.BICUBIC)
    original.putalpha(alpha)
    crop=original.crop((425,0,650,310))
    frame=Image.new('RGBA',(1024,1024));factor=min(880/crop.width,930/crop.height)
    crop=crop.resize((round(crop.width*factor),round(crop.height*factor)),Image.Resampling.LANCZOS)
    frame.alpha_composite(crop,((1024-crop.width)//2,(1024-crop.height)//2));frame.save(OUT/'head-input.png')
    texturing='--texture' in sys.argv
    workflow=json.loads((ROOT/'services/trellis/workflow_6gb.json').read_text())
    with (OUT/'head-input.png').open('rb') as f:
        r=client.post('/upload/image',files={'image':('task37-head-trial-20261023.png',f,'image/png')},data={'overwrite':'true'});r.raise_for_status();name=r.json()['name']
    workflow['6']['inputs']['image']=name
    workflow['55']['inputs'].update(remove_background=False,padding=0)
    workflow['19']['inputs']['filename_prefix']='Task37HeadTrial20261023'
    workflow['45']['inputs']['pipeline_type']='512'
    workflow['45']['inputs']['generate_texture_slat']=False
    if texturing:
        info=client.get('/object_info/Trellis2MeshTexturing_GGUF').json()['Trellis2MeshTexturing_GGUF']['input']['required']
        inputs={}
        for key,spec in info.items():
            if len(spec)>1 and isinstance(spec[1],dict) and 'default' in spec[1]:inputs[key]=spec[1]['default']
            elif isinstance(spec[0],list):inputs[key]=spec[0][0]
        inputs.update(pipeline=['39',0],image=['55',0],trimesh=['70',0],seed=109020838,texture_steps=20,resolution='1024',texture_size=2048,max_views=1,uv_unwrap_method='Smart',use_tiled_encoder=True,use_tiled_decoder_for_texture=True)
        workflow.pop('45');workflow.pop('54')
        workflow['70']={'class_type':'Trellis2LoadMesh_GGUF','inputs':{'glb_path':str(OUT/'head-400k.glb')}}
        workflow['71']={'class_type':'Trellis2MeshTexturing_GGUF','inputs':inputs}
        workflow['19']['inputs'].update(trimesh=['71',0],filename_prefix='Task37HeadTextured20261023')
    # Keep validated geometry/texture sampling. More pixels now represent head.
    (OUT/'workflow.json').write_text(json.dumps(workflow,indent=2))
    r=client.post('/prompt',json={'prompt':workflow,'client_id':'head-reconstruction-reviewed-trial'});r.raise_for_status();info=r.json();(OUT/'submission.json').write_text(json.dumps(info));pid=info['prompt_id'];print('submitted',pid,flush=True)
    start=time.monotonic()
    with (OUT/'memory.jsonl').open('w') as log:
        while time.monotonic()-start<2400:
            mem=memory();mem['elapsed']=time.monotonic()-start;log.write(json.dumps(mem)+'\n');log.flush()
            if mem['headroom_gib']<1.2:
                client.post('/interrupt',json={});raise RuntimeError('Interrupted trial at low commit headroom')
            history=client.get('/history/'+pid).json().get(pid)
            if history:
                (OUT/'history.json').write_text(json.dumps(history))
                status=history.get('status',{})
                if status.get('status_str')=='error':raise RuntimeError(str(status)[:1500])
                if status.get('completed'):
                    print('completed',flush=True);return
            if int(mem['elapsed'])%60<5: print(json.dumps(mem),flush=True)
            time.sleep(5)
    client.post('/interrupt',json={});raise TimeoutError('Head trial timed out')
if __name__=='__main__':main()
