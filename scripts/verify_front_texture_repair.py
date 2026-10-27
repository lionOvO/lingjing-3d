"""Check topology, hidden faces, UV direction and material in a tiny real GLB."""
from pathlib import Path
import tempfile
import sys
import numpy as np
import trimesh
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from repair_front_texture import repair, read_glb, accessor

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    mesh=trimesh.creation.box()
    mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new('RGB',(8,8),'blue')))
    source=root/'source.glb'
    mesh.export(source)
    reference=Image.new('RGBA',(64,64),(0,0,0,0))
    reference.paste((255,0,0,255),(8,8,56,32))
    reference.paste((0,255,0,255),(8,32,56,56))
    reference.save(root/'reference.png')
    output=root/'repaired.glb'
    repair(source,root/'reference.png',output)
    d,b=read_glb(output)
    primitives=d['meshes'][0]['primitives']
    front=primitives[1]
    vertices=accessor(d,b,front['attributes']['POSITION'])
    uv=accessor(d,b,front['attributes']['TEXCOORD_0'])
    front_faces=accessor(d,b,front['indices']).reshape(-1,3)
    assert len(front_faces)==2 and np.all(vertices[front_faces,2]==.5)
    assert uv[vertices[:,1]>.4,1].max()<.2
    assert uv[vertices[:,1]<-.4,1].min()>.8
    original,original_binary=read_glb(source)
    old_faces=accessor(original,original_binary,original['meshes'][0]['primitives'][0]['indices']).reshape(-1,3)
    new_faces=np.concatenate([accessor(d,b,p['indices']).reshape(-1,3) for p in primitives])
    assert sorted(map(tuple,old_faces))==sorted(map(tuple,new_faces))
    assert d['materials'][front['material']]['pbrMetallicRoughness']['metallicFactor']==0
    assert primitives[0]['attributes']['TEXCOORD_0']==original['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0']
print('PASS: exact topology, front visibility, hidden UV preservation, UV orientation, diffuse front material')
