import pytest
from app.models import GenerationTask, Project, User
from app.security import create_access_token


async def seed(db):
    owner = User(username="studio-owner", email="owner@example.test", password_hash="unused")
    other = User(username="studio-other", email="other@example.test", password_hash="unused")
    db.add_all([owner,other]); await db.flush()
    project = Project(user_id=owner.id, name="Owned project", project_type="anime_character")
    private = Project(user_id=other.id, name="Other project", project_type="anime_character")
    db.add_all([project,private]); await db.flush()
    good = GenerationTask(project_id=project.id, task_type="anime_character", status="completed", output_model_url="/api/v1/models/1/content", generation_params={"_artifact_object_name":"real.glb", "provider":"local_comfyui"})
    legacy = GenerationTask(project_id=project.id, task_type="anime_character", status="completed", output_model_url="mock://old")
    hidden = GenerationTask(project_id=private.id, task_type="anime_character", status="completed", output_model_url="mock://private")
    failed = GenerationTask(project_id=project.id, task_type="anime_character", status="failed")
    db.add_all([good,legacy,hidden,failed]); await db.commit()
    return owner,other,good,legacy,hidden,failed


@pytest.mark.asyncio
async def test_assets_require_auth_and_enforce_ownership(client,db_session):
    owner,other,good,legacy,hidden,failed = await seed(db_session)
    assert (await client.get('/api/v1/studio/assets')).status_code == 401
    headers={"Authorization":f"Bearer {create_access_token(owner.id)}"}
    records=(await client.get('/api/v1/studio/assets',headers=headers)).json()
    assert {row['id'] for row in records} == {good.id,legacy.id}
    assert '_artifact_object_name' not in records[1]['parameters']
    assert next(row for row in records if row['id']==legacy.id)['preview_available'] is False
    for task in [hidden,failed]:
        assert (await client.put(f'/api/v1/studio/assets/{task.id}',headers=headers,json={"name":"Forbidden","tags":[]})).status_code == 404
    assert (await client.get(f'/api/v1/studio/assets/{hidden.id}/file',headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_asset_trash_is_owned_recoverable_and_filters_before_pagination(client,db_session):
    owner,other,good,legacy,hidden,failed = await seed(db_session)
    headers={"Authorization":f"Bearer {create_access_token(owner.id)}"}
    foreign={"Authorization":f"Bearer {create_access_token(other.id)}"}
    assert (await client.delete(f'/api/v1/studio/assets/{good.id}')).status_code == 401
    for task in [hidden,failed]:
        assert (await client.delete(f'/api/v1/studio/assets/{task.id}',headers=headers)).status_code == 404
    assert (await client.delete(f'/api/v1/studio/assets/{good.id}',headers=foreign)).status_code == 404
    await client.put(f'/api/v1/studio/assets/{good.id}',headers=headers,json={"name":"My mesh","tags":["retained"]})
    for _ in range(2):
        assert (await client.delete(f'/api/v1/studio/assets/{good.id}',headers=headers)).json()['deleted'] is True
    active=(await client.get('/api/v1/studio/assets?limit=1',headers=headers)).json()
    assert [item['id'] for item in active]==[legacy.id]
    trash=(await client.get('/api/v1/studio/assets?deleted=true&limit=1',headers=headers)).json()
    assert [item['id'] for item in trash]==[good.id]
    assert trash[0]['name']=='My mesh' and trash[0]['tags']==['retained']
    await db_session.refresh(good)
    assert good.status.value=='completed' and good.generation_params['_artifact_object_name']=='real.glb'
    assert (await client.post(f'/api/v1/studio/assets/{good.id}/restore',headers=foreign)).status_code == 404
    for _ in range(2):
        assert (await client.post(f'/api/v1/studio/assets/{good.id}/restore',headers=headers)).json()['deleted'] is False
    assert (await client.get('/api/v1/studio/assets?deleted=true',headers=headers)).json()==[]
    restored=(await client.get('/api/v1/studio/assets',headers=headers)).json()
    assert next(item for item in restored if item['id']==good.id)['name']=='My mesh'


@pytest.mark.asyncio
async def test_asset_labels_persist_and_legacy_file_never_materializes(client,db_session,monkeypatch):
    from app import studio
    owner,_,good,legacy,_,_ = await seed(db_session)
    headers={"Authorization":f"Bearer {create_access_token(owner.id)}"}
    response=await client.put(f'/api/v1/studio/assets/{good.id}',headers=headers,json={"name":" Head ","tags":["角色","角色"," 纹理 "]})
    assert response.status_code == 200 and response.json()['tags'] == ['角色','纹理']
    records=(await client.get('/api/v1/studio/assets',headers=headers)).json()
    assert next(row for row in records if row['id']==good.id)['name'] == 'Head'
    assert (await client.put(f'/api/v1/studio/assets/{good.id}',headers=headers,json={"name":" ","tags":[]})).status_code == 422
    calls=[]
    async def get_object(name):
        calls.append(name); return b'original-stored-bytes','model/gltf-binary'
    monkeypatch.setattr(studio.storage,'get_object',get_object)
    assert (await client.get(f'/api/v1/studio/assets/{legacy.id}/file',headers=headers)).status_code == 404
    assert calls == []
    result=await client.get(f'/api/v1/studio/assets/{good.id}/file?download=true',headers=headers)
    assert result.content == b'original-stored-bytes' and 'attachment' in result.headers['content-disposition']


@pytest.mark.asyncio
async def test_preset_roundtrip_validation_and_owner_isolation(client,db_session):
    owner,other,*_ = await seed(db_session)
    headers={"Authorization":f"Bearer {create_access_token(owner.id)}"}
    foreign={"Authorization":f"Bearer {create_access_token(other.id)}"}
    payload={"name":"Standard","project_type":"anime_character","parameters":{"generation_mode":"high_quality","texture_resolution":"1024","mesh_density":"medium","pbr_enabled":True}}
    result=await client.post('/api/v1/studio/presets',headers=headers,json=payload)
    assert result.status_code == 201
    identifier=result.json()['id']
    assert (await client.get('/api/v1/studio/presets',headers=foreign)).json() == []
    assert (await client.put(f'/api/v1/studio/presets/{identifier}',headers=foreign,json=payload)).status_code == 404
    assert (await client.delete(f'/api/v1/studio/presets/{identifier}',headers=foreign)).status_code == 404
    payload['name']='Changed'; payload['parameters']['mesh_density']='low'
    assert (await client.put(f'/api/v1/studio/presets/{identifier}',headers=headers,json=payload)).json()['parameters']['mesh_density']=='low'
    payload['parameters']['generation_mode']='fast'
    assert (await client.post('/api/v1/studio/presets',headers=headers,json=payload)).status_code == 422
    payload['parameters']['generation_mode']='high_quality'; payload['parameters']['pbr_enabled']=False
    assert (await client.post('/api/v1/studio/presets',headers=headers,json=payload)).status_code == 422
    assert (await client.delete(f'/api/v1/studio/presets/{identifier}',headers=headers)).json()['archived'] is True
    assert (await client.get('/api/v1/studio/presets',headers=headers)).json() == []
