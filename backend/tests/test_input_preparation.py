"""Confirmed image bytes, task provenance and the image-only generation path."""
from types import SimpleNamespace

import pytest

from app import creation_tools, routers
from app.agents import CharacterAnalysisAgent, CharacterNormalizationAgent, RAGRetrievalAgent
from app.generation import GenerationEngineClient, build_generation_request
from app.models import Project
from app.security import create_access_token
from app.storage import StorageError
from tests.test_studio import seed


@pytest.mark.asyncio
async def test_task_input_works_before_completion_and_never_reads_another_users_file(client, db_session, monkeypatch):
    owner, other, task, legacy, _, _ = await seed(db_session)
    headers={'Authorization':f'Bearer {create_access_token(owner.id)}'}
    foreign={'Authorization':f'Bearer {create_access_token(other.id)}'}
    task.status='pending'
    task.generation_params={'_source_object_name':'confirmed.png','_original_source_object_name':'original.png'}
    await db_session.commit()
    calls=[]
    async def read(name):
        calls.append(name)
        return name.encode(),'image/png'
    monkeypatch.setattr(creation_tools.storage,'get_object',read)
    endpoint=f'/api/v1/studio/tasks/{task.id}/input'
    assert (await client.get(endpoint)).status_code==401
    assert (await client.get(endpoint,headers=foreign)).status_code==404
    assert calls==[]
    actual=await client.get(endpoint,headers=headers)
    original=await client.get(endpoint+'?original=true',headers=headers)
    assert actual.content==b'confirmed.png' and original.content==b'original.png'
    assert actual.headers['x-input-kind']=='snapshot'
    assert actual.headers['cache-control']=='private, no-store'
    assert (await client.get(f'/api/v1/studio/tasks/{legacy.id}/input?original=true',headers=headers)).status_code==404


@pytest.mark.asyncio
async def test_url_import_is_authenticated_cleans_temporary_object_and_does_not_queue(client,db_session,monkeypatch):
    owner,*_=await seed(db_session)
    headers={'Authorization':f'Bearer {create_access_token(owner.id)}'}
    deleted=[]
    async def upload(url): return SimpleNamespace(object_name='temporary.png')
    async def read(name): return b'image-pixels','image/png'
    async def delete(name): deleted.append(name)
    monkeypatch.setattr(creation_tools.storage,'upload_url',upload)
    monkeypatch.setattr(creation_tools.storage,'get_object',read)
    monkeypatch.setattr(creation_tools.storage,'delete',delete)
    monkeypatch.setattr(routers.generate_3d,'delay',lambda *a:pytest.fail('Preprocessing must not enqueue a GPU task'))
    endpoint='/api/v1/studio/images/import-url'
    payload={'url':'https://example.test/reference.png'}
    assert (await client.post(endpoint,json=payload)).status_code==401
    result=await client.post(endpoint,json=payload,headers=headers)
    assert result.status_code==200 and result.content==b'image-pixels'
    assert deleted==['temporary.png']
    async def broken(name): raise StorageError('private detail')
    monkeypatch.setattr(creation_tools.storage,'get_object',broken)
    result=await client.post(endpoint,json=payload,headers=headers)
    assert result.status_code==422 and 'private detail' not in result.text
    assert deleted==['temporary.png','temporary.png']


@pytest.mark.asyncio
@pytest.mark.parametrize('preparation',[
    {'version':1,'mode':'prepared','background':'white','background_removed':True},
    {'version':2,'mode':'prepared','strategy':'preserve-character','background':'preserve','background_removed':False,
     'enhance':False,'assessment':{'framing_method':'border-connected'},'review_warnings':[]},
])
async def test_confirmed_input_queues_exact_source_and_preserves_settings(client,db_session,monkeypatch,preparation):
    owner,_,good,*_=await seed(db_session)
    calls=[]
    monkeypatch.setattr(routers.generate_3d,'delay',lambda *args:(calls.append(args) or SimpleNamespace(id='test-queue-id')))
    monkeypatch.setattr(routers.storage,'object_name_from_url',lambda url:'confirmed-white.png')
    from tests.test_reference_tools import encode
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(80,100),'white');ImageDraw.Draw(image).rectangle((25,20,55,90),fill='red')
    async def stored(name):return encode(image),'image/png'
    monkeypatch.setattr(routers.storage,'get_object',stored)
    params={'generation_mode':'high_quality','texture_resolution':'1024','mesh_density':'medium','pbr_enabled':True,
        'input_preprocessed':True,'vision_analysis':False,'seed':109020838,'_original_source_object_name':'original.png',
        'image_preparation':preparation}
    result=await client.post('/api/v1/tasks',json={'project_id':good.project_id,'task_type':'anime_character',
        'source_image_url':'https://example.test/confirmed-white.png','output_format':'glb','generation_params':params})
    assert result.status_code==201
    record=result.json()
    assert calls==[(str(record['id']),'https://example.test/confirmed-white.png')]
    assert record['generation_params']['_source_object_name']=='confirmed-white.png'
    assert record['generation_params']['image_preparation']==params['image_preparation']
    state={'task_id':str(record['id']),'source_image_url':calls[0][1],'generation_params':record['generation_params']}
    def no_http(*a,**kw): pytest.fail('Confirmed images do not require vision HTTP calls')
    monkeypatch.setattr('app.agents.httpx.AsyncClient',no_http)
    state=await CharacterAnalysisAgent().run(state)
    state=await CharacterNormalizationAgent().run(state)
    state=await RAGRetrievalAgent().run(state)
    assert state['analysis_skipped'] is True and not state.get('error_message')
    outgoing=GenerationEngineClient._payload(build_generation_request(state))
    assert outgoing['input_image']=='https://example.test/confirmed-white.png'
    assert outgoing['input_preprocessed'] is True
    assert outgoing['texture_resolution']=='1024' and outgoing['mesh_density']=='medium'
    assert outgoing['pbr_enabled'] is True
    assert outgoing['seed']==109020838


@pytest.mark.asyncio
async def test_complex_original_cannot_hide_behind_plain_padding_or_claimed_removal(client,db_session,monkeypatch):
    import numpy as np
    from PIL import Image
    from tests.test_reference_tools import encode
    owner,_,good,*_=await seed(db_session)
    original=encode(Image.fromarray(np.random.default_rng(19).integers(0,256,(80,60,3),dtype=np.uint8)))
    padded=Image.new('RGB',(160,160),'white');padded.paste(Image.open(__import__('io').BytesIO(original)),(50,40))
    monkeypatch.setattr(routers.storage,'object_name_from_url',lambda url:'prepared.png')
    async def stored(name):return (original if name=='original.png' else encode(padded)),'image/png'
    monkeypatch.setattr(routers.storage,'get_object',stored)
    monkeypatch.setattr(routers.generate_3d,'delay',lambda *a:pytest.fail('Unsafe background must not enter GPU queue'))
    response=await client.post('/api/v1/tasks',json={'project_id':good.project_id,'task_type':'anime_character','source_image_url':'https://example.test/prepared.png',
        'generation_params':{'input_preprocessed':True,'_original_source_object_name':'original.png','image_preparation':{'background_removed':True}}})
    assert response.status_code==422 and '背景板' in response.json()['detail']


@pytest.mark.asyncio
async def test_explicit_background_acceptance_reaches_engine_with_exact_source(client,db_session,monkeypatch):
    import numpy as np
    from PIL import Image
    from tests.test_reference_tools import encode
    owner,_,good,*_=await seed(db_session)
    image=encode(Image.fromarray(np.random.default_rng(29).integers(0,256,(90,80,3),dtype=np.uint8)))
    async def stored(name):return image,'image/png'
    calls=[]
    monkeypatch.setattr(routers.storage,'get_object',stored)
    monkeypatch.setattr(routers.storage,'object_name_from_url',lambda url:'original.png')
    monkeypatch.setattr(routers.generate_3d,'delay',lambda *args:(calls.append(args) or SimpleNamespace(id='test-only')))
    payload={'project_id':good.project_id,'task_type':'object_model','source_image_url':'https://example.test/original.png',
        'generation_params':{'input_preprocessed':True,'vision_analysis':False,'image_preparation':{'mode':'original','assessment':{'background_kind':'complex'},'background_risk_accepted':'true'}}}
    assert (await client.post('/api/v1/tasks',json=payload)).status_code==422
    assert calls==[]
    payload['generation_params']['image_preparation']['background_risk_accepted']=True
    result=await client.post('/api/v1/tasks',json=payload)
    assert result.status_code==201
    params=result.json()['generation_params']
    assert params['_input_validation']['background_risk_accepted'] is True
    assert calls==[(str(result.json()['id']),'https://example.test/original.png')]
    outgoing=GenerationEngineClient._payload(build_generation_request({'task_id':str(result.json()['id']),'source_image_url':calls[0][1],'generation_params':params}))
    assert outgoing['image_preparation']['background_risk_accepted'] is True
    assert outgoing['input_image']=='https://example.test/original.png'
