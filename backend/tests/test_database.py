import pytest
from app.models import User
from app.security import hash_password


async def seed_user(db_session, username, email, password="correct horse battery"):
    user = User(username=username, email=email, password_hash=hash_password(password))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id":user.id, "username":user.username}


class FakeStorage:
    async def get_object(self, object_name):
        assert object_name == "generated/1/model.glb"
        return b"glTF", "model/gltf-binary"


class LegacyMockStorage:
    def __init__(self):
        self.uploads = []

    async def upload_generated_model(self, task_id, data, output_format):
        self.uploads.append((task_id, data, output_format))
        return f"generated/{task_id}/legacy.{output_format}"

    async def get_object(self, object_name):
        assert object_name == "generated/1/legacy.glb"
        return self.uploads[0][1], "model/gltf-binary"


@pytest.mark.asyncio
async def test_user_project_task_lifecycle(client, db_session):
    user = await seed_user(db_session, "test_user", "test@example.com")
    user_id = user["id"]

    project_response = await client.post("/api/v1/projects", json={
        "user_id": user_id,
        "name": "Demo character",
        "project_type": "anime_character",
    })
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    task_response = await client.post("/api/v1/tasks", json={
        "project_id": project_id,
        "task_type": "anime_character",
        "generation_params": {"quality": "high"},
    })
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    update_response = await client.patch(f"/api/v1/tasks/{task_id}", json={
        "status": "completed",
        "quality_score": 0.92,
        "output_model_url": "https://storage.example.com/model.glb",
    })
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "completed"
    assert update_response.json()["quality_score"] == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_validation_and_not_found(client):
    invalid = await client.post("/api/v1/users", json={"username": "x", "email": "bad", "password_hash": "short"})
    assert invalid.status_code == 422
    missing = await client.get("/api/v1/projects/99999")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_project_tasks_returns_only_its_history_newest_first(client, db_session):
    user = await seed_user(db_session, 'task_history_user', 'task-history@example.com')
    project = (await client.post("/api/v1/projects", json={
        "user_id": user["id"], "name": "Task history", "project_type": "anime_character",
    })).json()
    other_project = (await client.post("/api/v1/projects", json={
        "user_id": user["id"], "name": "Other history", "project_type": "object_model",
    })).json()
    first = (await client.post("/api/v1/tasks", json={
        "project_id": project["id"], "task_type": "anime_character",
    })).json()
    second = (await client.post("/api/v1/tasks", json={
        "project_id": project["id"], "task_type": "anime_character",
    })).json()
    await client.post("/api/v1/tasks", json={
        "project_id": other_project["id"], "task_type": "object_model",
    })

    listed = await client.get(f"/api/v1/projects/{project['id']}/tasks")
    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()] == [second["id"], first["id"]]
    assert all(task["project_id"] == project["id"] for task in listed.json())

    missing = await client.get("/api/v1/projects/99999/tasks")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_removes_dependent_task_records(client, db_session):
    user = await seed_user(db_session, 'delete_project_user', 'delete-project@example.com')
    project = (await client.post("/api/v1/projects", json={
        "user_id": user["id"], "name": "Disposable", "project_type": "anime_character",
    })).json()
    task = (await client.post("/api/v1/tasks", json={
        "project_id": project["id"], "task_type": "anime_character",
    })).json()

    # A completed generation persists both of these task-owned records.  The
    # project endpoint must remove them before deleting its generation task.
    feature = await client.put(f"/api/v1/tasks/{task['id']}/character-features", json={
        "character_type": "test", "style_tags": ["delete-test"],
    })
    metadata = await client.put(f"/api/v1/tasks/{task['id']}/metadata", json={
        "vertex_count": 3, "face_count": 1, "texture_resolution": "1024",
        "has_pbr": False, "file_size_mb": 0.01,
    })
    assert feature.status_code == 200
    assert metadata.status_code == 200

    deleted = await client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/projects/{project['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{task['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{task['id']}/character-features")).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{task['id']}/metadata")).status_code == 404


@pytest.mark.asyncio
async def test_rag_entry(client):
    response = await client.post("/api/v1/rag/entries", json={
        "collection_name": "character_style_collection",
        "milvus_id": "42",
        "entry_type": "character_style",
        "title": "Cel shading",
        "tags": ["anime", "pbr"],
    })
    assert response.status_code == 201
    listed = await client.get("/api/v1/rag/entries", params={"collection_name": "character_style_collection"})
    assert listed.status_code == 200
    assert listed.headers["x-total-count"] == "1"
    assert listed.json()[0]["title"] == "Cel shading"


@pytest.mark.asyncio
async def test_rag_search_queries_all_collections_unless_a_collection_is_selected(client):
    for collection_name, entry_type, title in (
        ("character_style_collection", "character_style", "角色风格规则"),
        ("generation_params_collection", "generation_params", "角色建模规则"),
    ):
        created = await client.post("/api/v1/rag/entries", json={
            "collection_name": collection_name,
            "milvus_id": collection_name,
            "entry_type": entry_type,
            "title": title,
            "content": "适用于角色生成",
        })
        assert created.status_code == 201

    all_results = await client.get("/api/v1/rag/search", params={"query": "角色"})
    assert {entry["title"] for entry in all_results.json()} == {"角色风格规则", "角色建模规则"}
    assert all_results.headers["x-total-count"] == "2"

    scoped_results = await client.get("/api/v1/rag/search", params={
        "query": "角色",
        "collection_name": "generation_params_collection",
    })
    assert [entry["title"] for entry in scoped_results.json()] == ["角色建模规则"]


@pytest.mark.asyncio
async def test_rag_search_supports_offset_and_reports_full_match_count(client):
    for number in range(3):
        created = await client.post("/api/v1/rag/entries", json={
            "collection_name": "generation_params_collection",
            "milvus_id": f"offset-{number}",
            "entry_type": "generation_params",
            "title": f"分页规则 {number}",
            "content": "用于分页测试",
        })
        assert created.status_code == 201

    response = await client.get("/api/v1/rag/search", params={"query": "分页规则", "offset": 2, "top_k": 1})
    assert response.status_code == 200
    assert response.headers["x-total-count"] == "3"
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_auth_login_refresh_me_for_legacy_account(client, db_session):
    await seed_user(db_session, 'auth_user', 'auth@example.com', 'correct horse battery')
    login = await client.post("/api/v1/auth/login", json={
        "username_or_email": "auth_user",
        "password": "correct horse battery",
    })
    assert login.status_code == 200
    tokens = login.json()
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "auth_user"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200


@pytest.mark.asyncio
async def test_auth_rejects_invalid_credentials(client, db_session):
    await seed_user(db_session, 'auth_user2', 'auth2@example.com', 'correct horse battery')
    response = await client.post("/api/v1/auth/login", json={
        "username_or_email": "auth_user2",
        "password": "wrong password",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "账号或密码错误"


@pytest.mark.asyncio
async def test_auth_login_strips_identifier_whitespace(client, db_session):
    await seed_user(db_session, 'trimmed_user', 'trimmed@example.com', 'correct horse battery')
    response = await client.post("/api/v1/auth/login", json={
        "username_or_email": "  trimmed_user  ",
        "password": "correct horse battery",
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_generated_model_is_delivered_through_api(client, db_session, monkeypatch):
    """The browser must never need access to Docker-internal MinIO URLs."""
    from app import routers

    monkeypatch.setattr(routers, "storage", FakeStorage())
    user = await seed_user(db_session, 'delivery_user', 'delivery@example.com')
    project = (await client.post("/api/v1/projects", json={
        "user_id": user["id"], "name": "Delivery", "project_type": "anime_character",
    })).json()
    task = (await client.post("/api/v1/tasks", json={
        "project_id": project["id"], "task_type": "anime_character",
    })).json()
    updated = await client.patch(f"/api/v1/tasks/{task['id']}", json={
        "status": "completed",
        "output_model_url": f"https://test.local/api/v1/models/{task['id']}/content",
        "generation_params": {"_artifact_object_name": "generated/1/model.glb"},
    })
    assert updated.status_code == 200

    preview = await client.get(f"/api/v1/models/{task['id']}/preview")
    assert preview.status_code == 200
    assert preview.json()["download_url"] == f"http://test/api/v1/models/{task['id']}/content"
    download = await client.get(f"/api/v1/models/{task['id']}/download")
    assert download.status_code == 200
    assert download.json()["download_url"].endswith("?download=true")
    content = await client.get(f"/api/v1/models/{task['id']}/content?download=true")
    assert content.status_code == 200
    assert content.content == b"glTF"
    assert "attachment" in content.headers["content-disposition"]


@pytest.mark.asyncio
async def test_legacy_mock_model_is_materialized_on_preview(client, db_session, monkeypatch):
    """Old completed tasks must be previewable after the worker contract changed."""
    from app import routers
    from app.models import GenerationTask, GenerationTaskStatus, OutputFormat

    storage = LegacyMockStorage()
    monkeypatch.setattr(routers, "storage", storage)
    user = await seed_user(db_session, 'legacy_user', 'legacy@example.com')
    project = (await client.post("/api/v1/projects", json={
        "user_id": user["id"], "name": "Legacy", "project_type": "anime_character",
    })).json()
    task = (await client.post("/api/v1/tasks", json={
        "project_id": project["id"], "task_type": "anime_character",
    })).json()
    task_record = await db_session.get(GenerationTask, task["id"])
    task_record.status = GenerationTaskStatus.COMPLETED
    task_record.output_format = OutputFormat.GLB
    task_record.output_model_url = "mock://3d-artifacts/legacy.glb"
    await db_session.commit()

    preview = await client.get(f"/api/v1/models/{task['id']}/preview")
    assert preview.status_code == 200
    assert preview.json()["download_url"] == f"http://test/api/v1/models/{task['id']}/content"
    assert len(storage.uploads) == 1
    assert storage.uploads[0][1][:4] == b"glTF"

    content = await client.get(f"/api/v1/models/{task['id']}/content")
    assert content.status_code == 200
    assert content.content[:4] == b"glTF"
    download = await client.get(f"/api/v1/models/{task['id']}/download")
    assert download.status_code == 200
    assert download.json()["download_url"].endswith("?download=true")
    assert len(storage.uploads) == 1
