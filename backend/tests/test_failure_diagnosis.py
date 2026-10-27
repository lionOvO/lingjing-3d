from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import failure_diagnosis as diagnosis
from app.models import GenerationTaskStatus
from app.security import create_access_token
from tests.test_studio import seed


@pytest.mark.parametrize("error,code", [
    ("ComfyUI execution failed: Allocation on device", "gpu_oom"),
    ("DefaultCPUAllocator: not enough memory", "host_memory"),
    ("MemoryError: Windows commit headroom low", "host_memory"),
    ("Server disconnected without sending a response", "engine_disconnected"),
    ("本机 3D 引擎在生成期间断开连接；请检查系统提交内存余量", "engine_disconnected"),
    ("ComfyUI [Errno 111] Connection refused", "engine_unreachable"),
    ("ReadTimeout: did not complete within 3300s", "timeout"),
    ("FileNotFoundError: checkpoint model.onnx", "missing_resource"),
    ("foreground 透明通道检查失败", "input_preparation"),
    ("ComfyUI completed without a GLB output; check node errors or CUDA OOM", "output_missing"),
    ("Task cancelled by user", "cancelled"),
    ("unexpected exception 0x9", "unknown"),
])
def test_error_evidence_does_not_confuse_disconnect_or_cpu_with_gpu(error, code):
    assert diagnosis.classify_error(error)[0] == code


def task(error="Server disconnected without sending a response", **params):
    return SimpleNamespace(id=37, status=GenerationTaskStatus.FAILED, error_message=error,
                           generation_params={"engine": "trellis2", "provider": "local_comfyui", **params})


def test_report_distinguishes_current_recovery_from_past_failure_and_unknown_peak():
    report = diagnosis.build_report(task(), {"adapter": "online", "engine": "online", "ram_free": 3 * 1024**3, "queue_running": 1, "queue_pending": 0}, [])
    assert report["classification"]["code"] == "engine_disconnected"
    assert "尚未确认" in report["classification"]["summary"]
    assert any("不代表上次任务成功" in item["value"] for item in report["evidence"])
    assert any("未采集失败瞬间" in item for item in report["limitations"])
    assert report["retrieval"]["hits"] == 1
    assert report["retrieval"]["external_model_used"] is False
    assert all("自动重试" not in action for action in report["actions"])


def test_unknown_error_and_different_provider_do_not_retrieve_irrelevant_cases():
    report = diagnosis.build_report(task("strange failure"), {"adapter": "unavailable"}, [])
    assert report["knowledge"] == []
    assert report["classification"]["code"] == "unknown"
    assert diagnosis.retrieve_knowledge("gpu_oom", {"provider": "huggingface_space"}) == []
    assert diagnosis.retrieve_knowledge("gpu_oom", {"engine": "triposr"}) == []


def test_error_redaction_and_only_safe_parameters_in_export():
    raw = 'https://user:pass@private.invalid/path?token=secret Bearer abc123 {"password":"hidden-value"} api_key=private-key sk-test-secret redis://u:p@redis:6379'
    cleaned = diagnosis.redact_error(raw)
    for value in ("private.invalid", "abc123", "hidden-value", "private-key", "sk-test-secret", "u:p"):
        assert value not in cleaned
    report = diagnosis.build_report(task(raw, _source_object_name="secret-image", api_key="hidden"), {}, [])
    assert "api_key" not in report["parameters"]
    assert "_source_object_name" not in report["parameters"]


def test_curated_sources_exist_and_claims_have_explicit_limits():
    root = Path(__file__).resolve().parents[2]
    entries = diagnosis.knowledge()["entries"]
    assert len({item["id"] for item in entries}) == len(entries)
    for item in entries:
        assert item["applicability"] and item["verification"] and item["actions"]
        for source in item["sources"]:
            assert (root / source["document"]).is_file()


@pytest.mark.asyncio
async def test_probe_has_bounded_read_only_request_and_whitelists_adapter(monkeypatch):
    class Adapter:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
            assert kwargs["timeout"].read == 7
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            assert url.endswith('/diagnostics')
            return httpx.Response(200, json={"engine": "online", "ram_free": 123, "vram_free": -1,
                                           "queue_running": True, "argv": ["secret"], "logs": "secret",
                                           "workflow_fingerprint": "a" * 16}, request=httpx.Request('GET', url))
    monkeypatch.setattr(diagnosis.httpx, 'AsyncClient', Adapter)
    result = await diagnosis.probe_runtime()
    assert result['engine'] == 'online' and result['ram_free'] == 123
    assert result['vram_free'] is None and result['queue_running'] is None
    assert 'argv' not in result and 'logs' not in result


@pytest.mark.asyncio
async def test_probe_outage_is_unknown_not_a_claim_of_memory_exhaustion(monkeypatch):
    class Adapter:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url): raise httpx.ConnectError("private endpoint")
    monkeypatch.setattr(diagnosis.httpx, 'AsyncClient', Adapter)
    assert await diagnosis.probe_runtime() == {"adapter": "unavailable", "engine": "unknown"}


@pytest.mark.asyncio
async def test_legacy_adapter_uses_only_explicit_read_only_bridge(monkeypatch):
    monkeypatch.setattr(diagnosis.settings, 'diagnostics_comfy_url', 'http://configured-bridge.test:8188')
    calls = []
    class Adapter:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            calls.append(url)
            body, status = {}, 404
            if url.endswith('system_stats'):
                body, status = {'system': {'ram_free': 321, 'argv': 'secret'}, 'devices': []}, 200
            elif url.endswith('queue'):
                body, status = {'queue_running': [['private prompt']], 'queue_pending': []}, 200
            return httpx.Response(status, json=body, request=httpx.Request('GET', url))
    monkeypatch.setattr(diagnosis.httpx, 'AsyncClient', Adapter)
    result = await diagnosis.probe_runtime()
    assert len(calls) == 3 and calls[1].startswith('http://configured-bridge.test:8188/')
    assert result['engine'] == 'online' and result['queue_running'] == 1
    assert result['ram_free'] == 321 and 'secret' not in str(result) and 'private prompt' not in str(result)
    report = diagnosis.build_report(task('Connection refused'), result, [])
    assert report['actions'][0].startswith('当前引擎仍有任务')
    assert any('无需仅因这条历史错误重启' in action for action in report['actions'])


@pytest.mark.asyncio
async def test_diagnosis_auth_ownership_and_no_generation_side_effects(client, db_session, monkeypatch):
    owner, other, good, _, hidden, failed = await seed(db_session)
    failed.error_message = 'CUDA out of memory'
    failed.generation_params = {'provider': 'local_comfyui', 'engine': 'trellis2', 'seed': 123}
    hidden.status = GenerationTaskStatus.FAILED
    hidden.error_message = failed.error_message
    hidden.generation_params = dict(failed.generation_params)
    await db_session.commit()
    calls = []
    async def probe():
        calls.append('probe')
        return {'adapter': 'online', 'engine': 'offline'}
    monkeypatch.setattr(diagnosis, 'probe_runtime', probe)
    path = f'/api/v1/studio/tasks/{failed.id}/diagnosis'
    headers = {'Authorization': f'Bearer {create_access_token(owner.id)}'}
    foreign = {'Authorization': f'Bearer {create_access_token(other.id)}'}
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=foreign)).status_code == 404
    assert (await client.get(f'/api/v1/studio/tasks/{hidden.id}/diagnosis', headers=headers)).status_code == 404
    assert (await client.get(f'/api/v1/studio/tasks/{good.id}/diagnosis', headers=headers)).status_code == 409
    assert calls == []
    response = await client.get(path, headers=headers)
    assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'
    report = response.json()
    assert report['classification']['code'] == 'gpu_oom'
    assert report['knowledge'][0]['id'] == 'gpu-memory'
    assert report['related_failures'] == []
    assert report['actions'][0].startswith('当前引擎仍无法连接')
    await db_session.refresh(failed)
    assert failed.status == GenerationTaskStatus.FAILED
    assert failed.generation_params['seed'] == 123 and failed.retry_count == 0 and failed.celery_task_id is None
    assert (await client.get('/api/v1/studio/diagnosis/knowledge')).status_code == 401
    library = await client.get('/api/v1/studio/diagnosis/knowledge', headers=headers)
    assert len(library.json()['entries']) == 8


@pytest.mark.asyncio
async def test_concurrent_retry_rejects_stale_failure_diagnosis(client, db_session, monkeypatch):
    owner, _, _, _, _, failed = await seed(db_session)
    async def probe():
        failed.status = GenerationTaskStatus.GENERATING
        await db_session.commit()
        return {'adapter': 'online', 'engine': 'online'}
    monkeypatch.setattr(diagnosis, 'probe_runtime', probe)
    response = await client.get(f'/api/v1/studio/tasks/{failed.id}/diagnosis', headers={'Authorization': f'Bearer {create_access_token(owner.id)}'})
    assert response.status_code == 409
