import hashlib
import io
import json
import struct

import httpx
import numpy as np
from PIL import Image
import pytest
import trimesh

from app import creation_tools
from app.mesh_tools import inspect_glb, repair_glb
from app.security import create_access_token
from tests.test_studio import seed


def textured_glb():
    box = trimesh.creation.box()
    mesh = trimesh.Trimesh(vertices=box.vertices, faces=np.vstack([box.faces, box.faces[0], [0,0,0]]), process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.array([[i % 2, (i//2) % 2] for i in range(len(mesh.vertices))]),
        material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new('RGB',(16,16),(201,74,65)),roughnessFactor=.8))
    scene = trimesh.Scene()
    scene.add_geometry(mesh, geom_name='textured-body', node_name='body', transform=trimesh.transformations.translation_matrix([2,1,0]))
    return scene.export(file_type='glb')


def test_mesh_repair_removes_bad_faces_and_preserves_uv_material_and_scene():
    data = textured_glb()
    report = inspect_glb(data)
    assert report['meshes'][0]['duplicate_faces'] == 1
    assert report['meshes'][0]['degenerate_faces'] == 1
    output, result = repair_glb(data,dict(clean_faces=True,fix_winding=True,fill_holes=True))
    assert result['after']['faces'] == result['before']['faces'] - 2
    assert result['after']['meshes'][0]['has_uv'] and result['after']['meshes'][0]['uv_valid']
    assert result['warnings']  # Textured holes are deliberately left alone.
    original = trimesh.load(io.BytesIO(data),file_type='glb',process=False,force='scene')
    repaired = trimesh.load(io.BytesIO(output),file_type='glb',process=False,force='scene')
    assert np.allclose(original.bounds,repaired.bounds)
    a,b=list(original.geometry.values())[0],list(repaired.geometry.values())[0]
    assert np.array_equal(a.visual.material.baseColorTexture,b.visual.material.baseColorTexture)
    assert np.array_equal(a.visual.uv,b.visual.uv)
    assert result['before']['sha256'] == hashlib.sha256(data).hexdigest()


def test_small_hole_repair_and_invalid_glb():
    box=trimesh.creation.box()
    box.update_faces(np.arange(len(box.faces)-1))
    data=box.export(file_type='glb')
    output, report=repair_glb(data,dict(clean_faces=True,fix_winding=True,fill_holes=True))
    assert report['before']['meshes'][0]['boundary_edges'] > 0
    assert report['after']['meshes'][0]['watertight'] is True
    with pytest.raises(ValueError): inspect_glb(b'broken')


def test_repair_rejects_animation_and_external_resources_before_loading():
    data=textured_glb()
    size=struct.unpack_from('<I',data,12)[0]
    document=json.loads(data[20:20+size])
    def pack(doc):
        chunk=json.dumps(doc).encode();chunk+=b' '*((-len(chunk))%4)
        tail=data[20+size:]
        return b'glTF'+struct.pack('<IIII',2,20+len(chunk)+len(tail),len(chunk),0x4E4F534A)+chunk+tail
    document['animations']=[{}]
    with pytest.raises(ValueError,match='静态模型'):
        repair_glb(pack(document),dict(clean_faces=True,fix_winding=True,fill_holes=False))
    del document['animations']
    document['images']=[{'uri':'https://untrusted.invalid/texture.png'}]
    with pytest.raises(ValueError,match='外部贴图'):
        inspect_glb(pack(document))


@pytest.mark.asyncio
async def test_inspect_repair_review_persist_and_other_user_isolation(client,db_session,monkeypatch):
    owner,other,good,legacy,hidden,_=await seed(db_session)
    headers={'Authorization':f'Bearer {create_access_token(owner.id)}'}
    foreign={'Authorization':f'Bearer {create_access_token(other.id)}'}
    objects={'real.glb':textured_glb()}
    original=objects['real.glb']
    async def get_object(name): return objects[name],'model/gltf-binary'
    async def put(task_id,data,fmt):
        name=f'repair-{len(objects)}.glb';objects[name]=data;return name
    monkeypatch.setattr(creation_tools.storage,'get_object',get_object)
    monkeypatch.setattr(creation_tools.storage,'upload_generated_model',put)
    prefix=f'/api/v1/studio/assets/{good.id}'
    assert (await client.post(prefix+'/inspect')).status_code==401
    assert (await client.post(prefix+'/inspect',headers=foreign)).status_code==404
    assert (await client.get(prefix+'/inspection',headers=headers)).json()['report'] is None
    report=await client.post(prefix+'/inspect',headers=headers)
    assert report.status_code==200 and report.json()['faces']==14
    assert (await client.post(f'/api/v1/studio/assets/{legacy.id}/inspect',headers=headers)).status_code==404
    payload={'name':'Clean version','clean_faces':True,'fix_winding':True,'fill_holes':False}
    response=await client.post(prefix+'/repair',headers=headers,json=payload)
    assert response.status_code==201
    revision=response.json()['id']
    assert response.json()['report']['after']['faces']==12
    saved=(await client.get(prefix+'/inspection',headers=headers)).json()
    assert len(saved['revisions'])==1
    assert 'object_name' not in saved['revisions'][0]
    path=f'{prefix}/revisions/{revision}/file'
    assert (await client.get(path,headers=foreign)).status_code==404
    downloaded=await client.get(path+'?download=true',headers=headers)
    assert downloaded.status_code==200 and downloaded.content[:4]==b'glTF'
    assert 'attachment' in downloaded.headers['content-disposition']
    assert objects['real.glb']==original
    assert (await client.put(prefix+'/review',headers=headers,json={'face':True,'note':'Check back next'})).status_code==200
    assert (await client.get(prefix+'/inspection',headers=headers)).json()['review']['face'] is True
    assert (await client.put(prefix+'/review',headers=foreign,json={'face':True})).status_code==404
    payload.update(clean_faces=False,fix_winding=False,fill_holes=False)
    assert (await client.post(prefix+'/repair',headers=headers,json=payload)).status_code==422


@pytest.mark.asyncio
async def test_reference_provenance_and_image_preparation_validation(client,db_session,monkeypatch):
    owner,_,good,_,_,_=await seed(db_session)
    headers={'Authorization':f'Bearer {create_access_token(owner.id)}'}
    assert (await client.get(f'/api/v1/studio/assets/{good.id}/reference',headers=headers)).status_code==404
    assert (await client.post('/api/v1/studio/images/remove-background',files={'image':('bad.png',b'bad','image/png')},headers=headers)).status_code==422
    image=Image.new('RGBA',(20,30),(255,0,0,0));buf=io.BytesIO();image.save(buf,'PNG')
    assert (await client.post('/api/v1/studio/images/remove-background',files={'image':('a.png',buf.getvalue(),'image/png')})).status_code==401
    # Only the internal foreground service is called, never /generate.
    calls=[]
    async def post(self,url,**kwargs):
        calls.append(url)
        return httpx.Response(200,content=buf.getvalue())
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    result=await creation_tools.remove_background(type('Upload',(),{'read':lambda self,n: _data(buf.getvalue())})(),owner)
    assert result.body==buf.getvalue() and calls[0].endswith('/prepare-image')


async def _data(value): return value
