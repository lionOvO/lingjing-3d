import base64
import importlib.util
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = Path(__file__).with_name("app.py")
SPEC = importlib.util.spec_from_file_location("trellis_adapter_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
adapter.GenerateRequest.model_rebuild(_types_namespace={"Any": Any})
adapter.Artifact.model_rebuild(_types_namespace={"Any": Any})
adapter.GenerateResponse.model_rebuild(_types_namespace={"Any": Any, "Artifact": adapter.Artifact})


@pytest.fixture(autouse=True)
def isolate_deployment_settings(monkeypatch):
    # Tests may share a process with backend settings loaded from the user's
    # .env. Never let its real provider/paths turn a unit test into inference.
    for name in ("TRELLIS_INFERENCE_COMMAND", "TRELLIS_PROVIDER", "TRELLIS_COMFY_ENABLED", "TRELLIS_HF_SPACE_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TRELLIS_COMFY_WORKFLOW", str(MODULE_PATH.with_name("workflow_6gb.json")))


def test_existing_alpha_is_preserved_without_starting_segmentation(tmp_path, monkeypatch):
    from PIL import Image
    source = tmp_path / 'transparent.png'
    Image.new('RGBA', (8, 8), (120, 100, 90, 0)).save(source)
    monkeypatch.setattr(adapter.subprocess, 'run', lambda *a, **kw: pytest.fail('already segmented'))
    before = source.read_bytes()
    assert adapter._prepare_comfy_input(source) == source
    assert source.read_bytes() == before


def test_diagnostics_reads_only_stats_and_queue_and_hides_prompts(monkeypatch):
    import httpx
    monkeypatch.setenv('TRELLIS_PROVIDER', 'local_comfyui')
    monkeypatch.setenv('TRELLIS_COMFY_ENABLED', 'true')
    requested = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {'timeout': 2, 'trust_env': False}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url):
            requested.append(url.rsplit('/', 1)[-1])
            body = {'system': {'ram_total': 16000, 'ram_free': 4000, 'argv': ['secret']},
                    'devices': [{'type': 'cuda', 'vram_free': 5000, 'vram_total': 6000}]} if url.endswith('system_stats') else {'queue_running': [['private prompt']], 'queue_pending': []}
            return httpx.Response(200, json=body, request=httpx.Request('GET', url))
    monkeypatch.setattr(adapter.httpx, 'Client', Client)
    result = adapter.diagnostics()
    assert requested == ['system_stats', 'queue']
    assert result['engine'] == 'online' and result['queue_running'] == 1
    assert result['ram_free'] == 4000 and result['vram_free'] == 5000
    assert result['workflow_ready'] is True and len(result['workflow_fingerprint']) == 16
    assert 'secret' not in str(result) and 'private prompt' not in str(result)


@pytest.mark.parametrize('exception,expected', [('ConnectError', 'offline'), ('ReadTimeout', 'unknown')])
def test_diagnostics_distinguishes_offline_from_timeout(monkeypatch, exception, expected):
    import httpx
    monkeypatch.setenv('TRELLIS_PROVIDER', 'local_comfyui')
    monkeypatch.setenv('TRELLIS_COMFY_ENABLED', 'true')
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): raise getattr(httpx, exception)('unavailable')
    monkeypatch.setattr(adapter.httpx, 'Client', Client)
    assert adapter.diagnostics()['engine'] == expected


def test_opaque_input_without_cached_model_fails_before_gpu_submission(tmp_path, monkeypatch):
    from PIL import Image
    source = tmp_path / 'opaque.jpg'
    Image.new('RGB', (8, 8), 'white').save(source)
    monkeypatch.setenv('U2NET_HOME', str(tmp_path / 'missing'))
    with pytest.raises(RuntimeError, match='isnet-anime.onnx'):
        adapter._prepare_comfy_input(source)


def test_missing_runner_is_an_explicit_error(monkeypatch, tmp_path):
    monkeypatch.delenv("TRELLIS_INFERENCE_COMMAND", raising=False)
    monkeypatch.setenv("TRELLIS_ARTIFACT_DIR", str(tmp_path))
    payload = adapter.GenerateRequest(task_id="t1", input_image="https://example.test/a.png")
    with pytest.raises(RuntimeError, match="TRELLIS_INFERENCE_COMMAND"):
        adapter.run_inference(payload)


def test_runner_writes_real_glb_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("TRELLIS_INFERENCE_COMMAND", "runner --input {input_image} --output {output_file}")
    monkeypatch.setenv("TRELLIS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("TRELLIS_INFERENCE_TIMEOUT", "30")

    def fake_download(_url, destination):
        destination.write_bytes(b"image")

    class Completed:
        returncode = 0
        stderr = ""

    def fake_run(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"glTF-real-model")
        return Completed()

    monkeypatch.setattr(adapter, "_download_image", fake_download)
    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    payload = adapter.GenerateRequest(task_id="t1", input_image="https://example.test/a.png")
    result = adapter.run_inference(payload)

    assert result.status == "completed"
    assert result.metadata["real_inference"] is True
    assert result.artifact_path and Path(result.artifact_path).read_bytes() == b"glTF-real-model"


def test_hf_space_provider_exports_a_real_glb_in_one_session(monkeypatch, tmp_path):
    monkeypatch.setenv("TRELLIS_HF_SPACE_ENABLED", "true")
    monkeypatch.setenv("TRELLIS_HF_SPACE_ID", "microsoft/TRELLIS.2")
    monkeypatch.setenv("TRELLIS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.delenv("TRELLIS_INFERENCE_COMMAND", raising=False)
    remote_glb = tmp_path / "remote.glb"
    remote_glb.write_bytes(b"glTF-from-hf-space")
    calls = []

    class FakeClient:
        def predict(self, *args, **kwargs):
            calls.append((args, kwargs))
            return None if kwargs["api_name"] == "/image_to_3d" else str(remote_glb)

        def close(self):
            calls.append(((), {"closed": True}))

    def fake_download(_url, destination):
        destination.write_bytes(b"image")

    monkeypatch.setattr(adapter, "_download_image", fake_download)
    monkeypatch.setattr(adapter, "_create_hf_client", lambda space_id: FakeClient())
    monkeypatch.setattr(adapter, "_hf_handle_file", lambda path: str(path))
    payload = adapter.GenerateRequest(task_id="remote-1", input_image="https://example.test/a.png", engine="trellis2", mode="high_quality")

    result = adapter.run_inference(payload)

    assert result.metadata["provider"] == "huggingface_space"
    assert result.artifact_path and Path(result.artifact_path).read_bytes() == b"glTF-from-hf-space"
    assert [call[1].get("api_name") for call in calls[:2]] == ["/image_to_3d", "/extract_glb"]


def test_hf_space_provider_rejects_non_glb_output(monkeypatch, tmp_path):
    monkeypatch.setenv("TRELLIS_HF_SPACE_ENABLED", "true")
    monkeypatch.setenv("TRELLIS_ARTIFACT_DIR", str(tmp_path))
    payload = adapter.GenerateRequest(task_id="remote-2", input_image="https://example.test/a.png", engine="trellis2", mode="high_quality", output_format="obj")

    with pytest.raises(RuntimeError, match="only supports GLB"):
        adapter._run_hf_space_inference(payload, tmp_path / "source.png", tmp_path / "model.obj")


def test_baked_obj_is_converted_to_a_binary_glb_with_texture(tmp_path):
    pytest.importorskip("trimesh")
    runner_path = Path(__file__).with_name("run_triposr.py")
    runner_spec = importlib.util.spec_from_file_location("triposr_runner_under_test", runner_path)
    assert runner_spec and runner_spec.loader
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    obj = tmp_path / "mesh.obj"
    obj.write_text(
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "vt 0 0\n"
        "vt 1 0\n"
        "vt 0 1\n"
        "f 1/1 2/2 3/3\n",
        encoding="ascii",
    )
    texture = tmp_path / "texture.png"
    texture.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="))
    output = tmp_path / "model.glb"

    runner.convert_baked_obj_to_glb(obj, texture, output)

    assert output.read_bytes()[:4] == b"glTF"
    assert output.stat().st_size > 100


@pytest.mark.parametrize('confirmed', [False, True])
def test_comfyui_prompt_uses_uploaded_image_and_project_settings(monkeypatch, tmp_path, confirmed):
    monkeypatch.setenv("TRELLIS_PROVIDER", "local_comfyui")
    monkeypatch.setenv("TRELLIS_COMFY_ENABLED", "true")
    monkeypatch.setenv("TRELLIS_COMFY_URL", "http://comfy:8188")
    monkeypatch.setenv("TRELLIS_ARTIFACT_DIR", str(tmp_path))
    calls = []

    class Response:
        def __init__(self, payload=None, content=b"", status_code=200):
            self._payload = payload
            self.content = content
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            if url.endswith("/upload/image"):
                if confirmed:
                    from PIL import Image
                    import io
                    uploaded = Image.open(io.BytesIO(kwargs['files']['image'][1].read()))
                    assert uploaded.convert('RGB').getpixel((0,0)) == (255,255,255)
                return Response({"name": "source-upload.png", "subfolder": "", "type": "input"})
            return Response({"prompt_id": "prompt-1"})

        def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            if "/history/" in url:
                return Response({"prompt-1": {"status": {"completed": True}, "outputs": {"19": {"gltf": [{"filename": "Trellis2Project.glb", "subfolder": "", "type": "output"}]}}}})
            return Response(content=b"glTF-local-comfy-model")

    def download_transparent(_url, destination):
        from PIL import Image
        Image.new('RGB' if confirmed else 'RGBA', (2, 2), 'white' if confirmed else (255, 0, 0, 0)).save(destination)

    monkeypatch.setattr(adapter, "_download_image", download_transparent)
    monkeypatch.setattr(adapter.httpx, "Client", Client)
    if confirmed:
        monkeypatch.setattr(adapter, '_prepare_comfy_input', lambda *a: pytest.fail('White confirmed input must not be segmented again'))
    payload = adapter.GenerateRequest(task_id="local-1", input_image="https://example.test/a.png", engine="trellis2", mode="high_quality", input_preprocessed=confirmed)

    result = adapter.run_inference(payload)

    assert result.metadata["provider"] == "local_comfyui"
    assert result.artifact_path and Path(result.artifact_path).read_bytes() == b"glTF-local-comfy-model"
    prompt_call = next(call for call in calls if call[0] == "POST" and call[1].endswith("/prompt"))
    prompt = prompt_call[2]["json"]["prompt"]
    assert prompt["6"]["inputs"]["image"] == "source-upload.png"
    assert prompt['55']['inputs']['remove_background'] is False
    assert prompt['55']['inputs']['padding'] == (0 if confirmed else 25)
    assert prompt["45"]["inputs"]["pipeline_type"] == "1024_cascade"
    assert prompt["45"]["inputs"]["generate_texture_slat"] is True
    assert prompt["19"]["inputs"]["filename_prefix"].startswith("Trellis2Project-")


def test_comfyui_provider_requires_explicit_enable(monkeypatch):
    monkeypatch.delenv("TRELLIS_COMFY_ENABLED", raising=False)
    monkeypatch.delenv("TRELLIS_PROVIDER", raising=False)
    payload = adapter.GenerateRequest(task_id="local-2", input_image="https://example.test/a.png")
    assert adapter._use_local_comfyui(payload) is False


@pytest.mark.parametrize('error_type, message', [
    (adapter.httpx.ConnectError, '引擎连接失败，可能未启动或已经退出'),
    (adapter.httpx.RemoteProtocolError, '引擎在生成期间断开连接'),
])
def test_engine_exit_is_explained_without_resubmitting(monkeypatch, tmp_path, error_type, message):
    source = tmp_path / 'input.png'
    source.write_bytes(b'isolated transport test')
    monkeypatch.setattr(adapter, '_prepare_comfy_input', lambda path: path)
    calls = []

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, **kwargs):
            calls.append(url)
            raise error_type('transport stopped')

    monkeypatch.setattr(adapter.httpx, 'Client', Client)
    payload = adapter.GenerateRequest(task_id='test-only', input_image='https://example.test/a.png')
    with pytest.raises(RuntimeError, match=message):
        adapter._run_local_comfyui_inference(payload, source, tmp_path / 'output.glb', 'test')
    assert len(calls) == 1


def test_capabilities_only_enables_the_configured_local_mode(monkeypatch):
    monkeypatch.setenv("TRELLIS_PROVIDER", "local_comfyui")
    monkeypatch.setenv("TRELLIS_COMFY_ENABLED", "true")
    monkeypatch.delenv("TRELLIS_INFERENCE_COMMAND", raising=False)

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return adapter.httpx.Response(200, request=adapter.httpx.Request("GET", url))

    monkeypatch.setattr(adapter.httpx, "Client", Client)
    result = adapter.capabilities()
    assert result["available_modes"] == ["high_quality"]
    assert result["default_texture_resolution"] == "1024"
    assert result["pbr_required"] is True
    assert result["experimental_texture_resolutions"] == ["2048"]


def test_capabilities_reports_offline_comfyui_as_unavailable(monkeypatch):
    monkeypatch.setenv("TRELLIS_PROVIDER", "local_comfyui")
    monkeypatch.setenv("TRELLIS_COMFY_ENABLED", "true")
    monkeypatch.delenv("TRELLIS_INFERENCE_COMMAND", raising=False)

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            raise adapter.httpx.ConnectError("offline")

    monkeypatch.setattr(adapter.httpx, "Client", Client)
    with pytest.raises(adapter.HTTPException) as error:
        adapter.capabilities()
    assert error.value.status_code == 503


def test_medium_1024_prompt_matches_verified_round5_parameters():
    payload = adapter.GenerateRequest(input_image="source.png", texture_resolution="1024", mesh_density="medium")
    prompt = adapter._build_comfy_prompt("source.png", "regression", payload)
    assert prompt["45"]["inputs"]["shape_steps"] == 16
    assert prompt["45"]["inputs"]["texture_steps"] == 20
    assert prompt["54"]["inputs"]["texture_size"] == 1024
    assert prompt["54"]["inputs"]["target_face_num"] == 500000


def test_existing_alpha_mask_skips_only_redundant_background_removal():
    payload = adapter.GenerateRequest(input_image="source.png", texture_resolution="1024")
    transparent = adapter._build_comfy_prompt("source.png", "test", payload, has_transparency=True)
    opaque = adapter._build_comfy_prompt("source.png", "test", payload)
    assert transparent["55"]["inputs"]["remove_background"] is False
    assert opaque["55"]["inputs"]["remove_background"] is True
    assert transparent["45"] == opaque["45"]
    assert transparent["54"] == opaque["54"]


def test_confirmed_alpha_preserves_crop_margin_and_uses_existing_rgb_background(tmp_path):
    from PIL import Image
    original=tmp_path/'confirmed.png'
    image=Image.new('RGBA',(100,160),(255,255,255,0))
    image.putpixel((50,80),(200,80,40,128))
    image.save(original)
    before=original.read_bytes()
    normalized=Image.open(adapter._confirmed_comfy_input(original))
    assert normalized.mode=='RGB' and normalized.size==(100,160)
    assert normalized.getpixel((0,0))==(0,0,0)
    assert normalized.getpixel((50,80))==(100,40,20)
    assert original.read_bytes()==before


def test_export_nonce_and_density_do_not_change_sampling_or_template():
    seed=1039624827
    payload=adapter.GenerateRequest(input_image='source.png',seed=seed,mesh_density='low')
    a=adapter._build_comfy_prompt('same.png','first-export',payload)
    b=adapter._build_comfy_prompt('same.png','second-export',payload)
    assert a['45']==b['45']
    assert a['45']['inputs']['seed']==seed
    assert a['45']['inputs']['texture_steps']==20
    assert a['19']!=b['19']
    assert adapter._load_comfy_workflow()['45']['inputs']['seed']==109020838


def test_known_complex_background_fails_before_comfy_upload(tmp_path,monkeypatch):
    from PIL import Image
    source=tmp_path/'opaque.png';Image.new('RGB',(16,16),'gray').save(source)
    with pytest.raises(RuntimeError,match='背景'):
        adapter._confirmed_comfy_input(source,requires_foreground=True)


def test_explicit_background_acceptance_preserves_original_pixels(tmp_path):
    from PIL import Image
    source=tmp_path/'original.png'
    image=Image.new('RGB',(32,24),(120,90,50));image.putpixel((16,2),(230,160,60));image.save(source)
    result=Image.open(adapter._confirmed_comfy_input(source,requires_foreground=True,background_risk_accepted=True))
    assert result.size==image.size and result.tobytes()==image.tobytes()
    with pytest.raises(RuntimeError):
        adapter._confirmed_comfy_input(source,requires_foreground=True,background_risk_accepted='true')


def test_anime_segmentation_confidence_does_not_fade_opaque_clothing(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from PIL import Image
    source=tmp_path/'person.png'
    Image.new('RGB',(3,1),(80,120,200)).save(source)
    (tmp_path/'isnet-anime.onnx').touch()
    monkeypatch.setenv('U2NET_HOME',str(tmp_path))
    def session(name,providers):
        assert name=='isnet-anime' and providers==['CPUExecutionProvider']
        return object()
    def segment(image,session):
        result=image.convert('RGBA');alpha=Image.new('L',image.size)
        alpha.putdata([0,80,255]);result.putalpha(alpha)
        return result
    monkeypatch.setitem(sys.modules,'rembg',SimpleNamespace(new_session=session,remove=segment))
    def run(command,**kwargs):
        assert kwargs['env']['OMP_NUM_THREADS']=='2'
        with monkeypatch.context() as local:
            local.setattr(sys,'argv',['-c',*command[3:]])
            exec(command[2],{})
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(adapter.subprocess,'run',run)
    result=Image.open(adapter._prepare_comfy_input(source))
    assert result.getpixel((0,0))[3]==0
    assert result.getpixel((1,0))==(80,120,200,255)
    assert result.getpixel((2,0))==(80,120,200,255)
