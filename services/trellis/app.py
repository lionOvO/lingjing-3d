"""HTTP adapter for a real TRELLIS-2/TripoSR inference runner.

The image-to-3D model is supplied by the deployment. The adapter downloads
the uploaded image, invokes ``TRELLIS_INFERENCE_COMMAND`` and returns the
generated file through a shared artifact directory. It never fabricates a
mesh when the model is missing.
"""
from __future__ import annotations

import hashlib
import base64
import threading
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

app = FastAPI(title="TRELLIS-2 / TripoSR adapter", version="1.0.0")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("trellis.adapter")
prepare_lock = threading.Lock()


class PrepareImageRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=28_000_000)
    model: Literal['isnet-anime', 'u2net'] = 'isnet-anime'


@app.post("/prepare-image")
def prepare_image(payload: PrepareImageRequest):
    """CPU-only foreground preview, never submits a ComfyUI generation prompt."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    import io
    if not prepare_lock.acquire(blocking=False):
        raise HTTPException(429, "Background removal busy")
    try:
        try:
            data = base64.b64decode(payload.image_base64, validate=True)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError()
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 20_000_000:
                    raise ValueError()
                normalized = ImageOps.exif_transpose(image).convert("RGBA")
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise HTTPException(422, "Invalid image") from None
        with tempfile.TemporaryDirectory(prefix="lingjing-prepare-") as temp:
            source = Path(temp) / "source.png"
            normalized.save(source)
            output = _prepare_comfy_input(source, model=payload.model)
            return Response(output.read_bytes(), media_type="image/png", headers={'X-Foreground-Model': payload.model})
    except (RuntimeError, subprocess.TimeoutExpired):
        raise HTTPException(503, "CPU foreground extraction unavailable") from None
    finally:
        prepare_lock.release()


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str | None = None
    input_image: str | None = Field(default=None, min_length=1, max_length=2000)
    source_image_url: str | None = Field(default=None, min_length=1, max_length=2000)
    engine: str = Field(default="trellis2", min_length=1, max_length=30)
    output_format: str = Field(default="glb", min_length=2, max_length=10)
    mode: str = Field(default="high_quality", min_length=1, max_length=30)
    texture_resolution: str = Field(default="2048", min_length=2, max_length=20)
    mesh_density: str = Field(default="medium", min_length=1, max_length=20)
    pbr_enabled: bool = True
    input_preprocessed: bool = False
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    image_preparation: dict[str, Any] | None = None
    character_params: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_image(self) -> "GenerateRequest":
        if not self.input_image:
            self.input_image = self.source_image_url
        if not self.input_image:
            raise ValueError("input_image or source_image_url is required")
        return self

    @field_validator("output_format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.lower().lstrip(".")
        if normalized not in {"glb", "obj", "ply", "fbx", "stl"}:
            raise ValueError("unsupported output format")
        return normalized

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, value: str) -> str:
        normalized = value.lower().replace("-", "")
        if normalized not in {"trellis2", "triposr"}:
            raise ValueError("engine must be trellis2 or triposr")
        return normalized


class Artifact(BaseModel):
    model_url: str
    texture_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    status: str
    engine: str
    job_id: str
    model_url: str
    artifact_path: str | None = None
    texture_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "engine": "trellis-2"}


@app.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    """Bounded, read-only snapshot. Never return prompts, argv, or raw logs."""
    result: dict[str, Any] = {"engine": "unknown"}
    probe = GenerateRequest(input_image="diagnostic-check", texture_resolution="1024")
    if not _use_local_comfyui(probe) or os.getenv("TRELLIS_INFERENCE_COMMAND", "").strip():
        return {"engine": "not_applicable"}
    try:
        workflow = _load_comfy_workflow()
        result["workflow_ready"] = all(key in workflow for key in ("6", "39", "45", "54", "19"))
        result["workflow_fingerprint"] = hashlib.sha256(json.dumps(workflow, sort_keys=True).encode()).hexdigest()[:16]
    except (OSError, ValueError, RuntimeError):
        result["workflow_ready"] = False

    def byte_count(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**60 else None

    with httpx.Client(timeout=2, trust_env=False) as client:
        try:
            response = client.get(f"{_comfy_url()}/system_stats")
            response.raise_for_status()
            stats = response.json()
            if not isinstance(stats, dict) or not isinstance(stats.get("system"), dict):
                raise ValueError("invalid system stats")
            result["engine"] = "online"
            result["ram_total"] = byte_count(stats["system"].get("ram_total"))
            result["ram_free"] = byte_count(stats["system"].get("ram_free"))
            device = next((item for item in stats.get("devices", []) if isinstance(item, dict) and item.get("type") == "cuda"), {})
            result["vram_total"] = byte_count(device.get("vram_total"))
            result["vram_free"] = byte_count(device.get("vram_free"))
        except httpx.ConnectError:
            result["engine"] = "offline"
        except (httpx.HTTPError, ValueError, TypeError):
            # Timeout/protocol errors do not prove that the process exited.
            result["engine"] = "unknown"
        try:
            response = client.get(f"{_comfy_url()}/queue")
            response.raise_for_status()
            queue = response.json()
            for name in ("running", "pending"):
                rows = queue.get(f"queue_{name}")
                if isinstance(rows, list):
                    result[f"queue_{name}"] = len(rows)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
    return result


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    probe = GenerateRequest(input_image="capability-check", texture_resolution="1024")
    local = _use_local_comfyui(probe) and not os.getenv("TRELLIS_INFERENCE_COMMAND", "").strip()
    if local:
        try:
            workflow = _load_comfy_workflow()
            with httpx.Client(timeout=5, trust_env=False) as client:
                client.get(f"{_comfy_url()}/system_stats").raise_for_status()
            if not all(key in workflow for key in ("6", "39", "45", "54", "19")):
                raise ValueError("工作流缺少必要节点")
        except (OSError, ValueError, RuntimeError, httpx.HTTPError) as error:
            raise HTTPException(status_code=503, detail="本机 ComfyUI 或工作流尚未就绪") from error
        return {"provider": "local_comfyui", "workflow": "Pixal3D 1024 cascade",
                "available_modes": ["high_quality"], "default_mode": "high_quality",
                "texture_resolutions": ["1024", "2048"], "experimental_texture_resolutions": ["2048"],
                "default_texture_resolution": "1024", "default_mesh_density": "medium",
                "default_seed": workflow['45']['inputs']['seed'],
                "mesh_face_targets": {"low": 300000, "medium": 500000, "high": 700000},
                "pbr_required": True, "output_format": "glb"}
    raise HTTPException(status_code=503, detail="当前部署尚未接入已验证的本机高质量工作流")


def run_inference(payload: GenerateRequest) -> GenerateResponse:
    """Invoke the deployment's actual image-to-3D runner.

    The command receives an input image and an output path. A typical value is
    ``python /app/run_triposr.py --input {input_image} --output
    {output_file}``. Keeping the runner behind this contract lets the service
    work with either the official TRELLIS-2 or TripoSR implementation without
    embedding their incompatible CUDA stacks in the API adapter.
    """
    artifact_dir = Path(os.getenv("TRELLIS_ARTIFACT_DIR", "/artifacts")).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{payload.task_id}:{payload.input_image}:{payload.engine}".encode()).hexdigest()[:16]
    output_path = artifact_dir / f"{digest}.{payload.output_format}"
    command_template = os.getenv("TRELLIS_INFERENCE_COMMAND", "").strip()
    # An explicit command is the most specific deployment choice. This also
    # keeps local test/dev overrides from being hijacked by a .env provider.
    is_hf_space = _use_hf_space(payload) and not command_template
    is_comfyui = _use_local_comfyui(payload) and not command_template
    if not is_hf_space and not is_comfyui:
        if not command_template:
            raise RuntimeError("TRELLIS_INFERENCE_COMMAND is not configured; mount a real TRELLIS-2 or TripoSR runner, or enable TRELLIS_HF_SPACE_ENABLED for high-quality GLB tests")
    with tempfile.TemporaryDirectory(prefix=f"input-{digest}-") as temp_dir:
        input_path = Path(temp_dir) / "source-image.png"
        _download_image(payload.input_image or payload.source_image_url or "", input_path)
        if is_hf_space:
            _run_hf_space_inference(payload, input_path, output_path)
        elif is_comfyui:
            _run_local_comfyui_inference(payload, input_path, output_path, digest)
        else:
            command = _format_command(command_template, payload, input_path, output_path, digest)
            logger.info("Starting local %s inference task_id=%s command=%s", payload.engine, payload.task_id, command)
            completed = subprocess.run(command, capture_output=True, text=True, timeout=_inference_timeout())
            if completed.returncode != 0:
                logger.error("Inference runner failed task_id=%s stderr=%s", payload.task_id, completed.stderr[-4000:])
                raise RuntimeError(f"{payload.engine} inference failed with exit code {completed.returncode}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Inference runner did not produce {output_path.name}")
    metadata = {
        "engine": payload.engine,
        "model_path": os.getenv("TRELLIS2_MODEL_PATH" if payload.engine == "trellis2" else "TRIPOSR_MODEL_PATH", ""),
        "provider": "huggingface_space" if is_hf_space else "local_comfyui" if is_comfyui else "local_runner",
        "provider_model": os.getenv("TRELLIS_HF_SPACE_ID", "microsoft/TRELLIS.2") if is_hf_space else os.getenv("TRELLIS_COMFY_WORKFLOW") if is_comfyui else None,
        "real_inference": True,
        "file_size_bytes": output_path.stat().st_size,
        "texture_resolution": payload.texture_resolution,
        "has_pbr": True if is_comfyui else payload.pbr_enabled,
        "sampling_seed": (payload.seed if payload.seed is not None else _load_comfy_workflow()['45']['inputs']['seed']) if is_comfyui else None,
    }
    artifact = Artifact(model_url=f"artifact://{digest}", metadata=metadata)
    return GenerateResponse(status="completed", engine=payload.engine, job_id=digest, model_url=artifact.model_url, artifact_path=str(output_path), metadata=metadata, artifacts=[artifact])


def _use_hf_space(payload: GenerateRequest) -> bool:
    """Keep public Space use explicit and limited to high-quality GLB jobs.

    The Microsoft demo's export endpoint only guarantees GLB. Restricting it
    here prevents a request for OBJ/FBX/STL from silently receiving a GLB
    under a misleading extension.
    """
    enabled = os.getenv("TRELLIS_HF_SPACE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and payload.engine == "trellis2" and payload.mode == "high_quality"


def _use_local_comfyui(payload: GenerateRequest) -> bool:
    """Use a locally running ComfyUI only when explicitly configured.

    ComfyUI is commonly installed on the Windows host while this adapter runs
    in Docker. Keeping the provider opt-in prevents an unreachable default URL
    from turning every high-quality task into a long retry cycle.
    """
    provider = os.getenv("TRELLIS_PROVIDER", "command").strip().lower().replace("-", "_")
    enabled = os.getenv("TRELLIS_COMFY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return (
        enabled
        and provider in {"local_comfyui", "comfyui", "comfy"}
        and payload.engine == "trellis2"
        and payload.output_format == "glb"
    )


def _comfy_url() -> str:
    return os.getenv("TRELLIS_COMFY_URL", "http://host.docker.internal:8188").strip().rstrip("/")


def _comfy_timeout() -> float:
    try:
        return max(30.0, float(os.getenv("TRELLIS_COMFY_TIMEOUT", "2400")))
    except ValueError:
        return 2400.0


def _comfy_poll_interval() -> float:
    try:
        return max(0.25, float(os.getenv("TRELLIS_COMFY_POLL_INTERVAL", "2")))
    except ValueError:
        return 2.0


def _comfy_workflow_path() -> Path:
    configured = os.getenv("TRELLIS_COMFY_WORKFLOW", "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file() or candidate.is_absolute() and os.name != "nt":
            return candidate
    return Path(__file__).with_name("workflow_6gb.json")


def _comfy_output_dir() -> Path | None:
    configured = os.getenv("TRELLIS_COMFY_OUTPUT_DIR", "").strip()
    if not configured:
        return None
    candidate = Path(configured)
    return candidate if candidate.is_dir() else None


def _load_comfy_workflow() -> dict[str, Any]:
    path = _comfy_workflow_path()
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"ComfyUI workflow file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ComfyUI workflow file is invalid JSON: {path}") from exc
    if not isinstance(workflow, dict) or not workflow:
        raise RuntimeError(f"ComfyUI workflow must be a non-empty object: {path}")
    return workflow


def _build_comfy_prompt(image_name: str, digest: str, payload: GenerateRequest, *, has_transparency: bool = False) -> dict[str, Any]:
    """Fill the API-format workflow without mutating the on-disk template."""
    workflow = json.loads(json.dumps(_load_comfy_workflow()))
    image_node = workflow.get("6")
    export_node = workflow.get("19")
    if not isinstance(image_node, dict) or not isinstance(export_node, dict):
        raise RuntimeError("ComfyUI workflow must contain image node 6 and export node 19")
    image_node.setdefault("inputs", {})["image"] = image_name
    if has_transparency and isinstance(workflow.get("55"), dict):
        # An existing alpha mask is already a background-removal result.
        # Running the large segmentation model again wastes RAM and can OOM.
        workflow["55"].setdefault("inputs", {})["remove_background"] = False
    if payload.input_preprocessed and isinstance(workflow.get("55"), dict):
        # The browser already chose the framing. Confirmed inputs are RGB
        # below, so this node cannot crop again around their alpha mask.
        workflow["55"].setdefault("inputs", {}).update(remove_background=False, padding=0)
    export_node.setdefault("inputs", {})["filename_prefix"] = f"Trellis2Project-{digest}"
    # The project exposes texture resolution and density; the validated 6 GB
    # workflow maps those values to its stable GLB post-processing settings.
    generator = workflow.get("45")
    postprocess = workflow.get("54")
    if isinstance(generator, dict):
        inputs = generator.setdefault("inputs", {})
        # Unique export names are independent of sampling. Density controls
        # exported faces, not an unannounced change in inference quality.
        if payload.seed is not None:
            inputs["seed"] = payload.seed
    if isinstance(postprocess, dict):
        inputs = postprocess.setdefault("inputs", {})
        try:
            requested_texture = int(payload.texture_resolution)
        except (TypeError, ValueError):
            requested_texture = 2048
        inputs["texture_size"] = 2048 if requested_texture >= 2048 else 1024
        inputs["target_face_num"] = {"low": 300000, "medium": 500000, "high": 700000}.get(payload.mesh_density, 500000)
    return workflow


def _prepare_comfy_input(input_path: Path, *, model: str = 'isnet-anime') -> Path:
    """Preserve alpha, otherwise segment on CPU before loading GPU models.

    A short-lived subprocess releases ONNX's allocator before ComfyUI starts.
    The model must be cached locally; inference never downloads weights.
    """
    from PIL import Image
    with Image.open(input_path) as image:
        if image.convert('RGBA').getchannel('A').getextrema()[0] < 255:
            return input_path
    if model not in {'isnet-anime', 'u2net'}:
        raise RuntimeError('不支持的前景分割模型')
    model_path = Path(os.getenv('U2NET_HOME', str(Path.home() / '.u2net'))) / f'{model}.onnx'
    if not model_path.is_file():
        raise RuntimeError(f'本机抠图模型 {model}.onnx 缺失，请先配置 U2NET_HOME；未提交 GPU 任务')
    prepared = input_path.with_name(input_path.stem + '-foreground.png')
    code = """import sys
from PIL import Image, ImageOps
from rembg import new_session, remove
session = new_session(sys.argv[3], providers=['CPUExecutionProvider'])
with Image.open(sys.argv[1]) as image:
    result = remove(ImageOps.exif_transpose(image).convert('RGB'), session=session)
    alpha = result.getchannel('A')
    if sys.argv[3] == 'isnet-anime':
        # Segmentation confidence is not cloth opacity. Retain low-confidence
        # anime sleeves without fading their original RGB into the black input.
        alpha = alpha.point(lambda v: 0 if v <= 12 else 255 if v >= 32 else round((v - 12) * 255 / 20))
        result.putalpha(alpha)
    if alpha.getextrema()[1] == 0:
        raise RuntimeError('Background removal found no foreground')
    result.save(sys.argv[2], 'PNG')
"""
    env = os.environ.copy()
    env['OMP_NUM_THREADS'] = '2'
    result = subprocess.run([sys.executable, '-c', code, str(input_path), str(prepared), model],
                            env=env, capture_output=True, text=True, timeout=180)
    if result.returncode or not prepared.is_file():
        logger.error('CPU background removal failed: %s', result.stderr[-2000:])
        raise RuntimeError('本机 CPU 抠图失败，未提交 GPU 任务；请检查生成服务日志或上传透明背景 PNG')
    return prepared


def _confirmed_comfy_input(input_path: Path, *, requires_foreground: bool = False, background_risk_accepted: bool = False) -> Path:
    """Flatten alpha for the RGB conditioner, preserving the confirmed framing.

    This matches the existing node's black alpha composition, without its
    automatic alpha bounding-box crop. White pixels remain white.
    The original confirmed PNG is retained separately by object storage.
    """
    from PIL import Image, ImageOps
    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
        if requires_foreground and background_risk_accepted is not True and image.getchannel('A').getextrema()[0] >= 250:
            raise RuntimeError('参考图仍含复杂背景，请先确认完整的透明前景；未提交 GPU 任务')
        background = Image.new('RGBA', image.size, (0, 0, 0, 255))
        result = Image.alpha_composite(background, image).convert('RGB')
        destination = input_path.with_name(input_path.stem + '-conditioning.png')
        result.save(destination)
    return destination


def _run_local_comfyui_inference(payload: GenerateRequest, input_path: Path, output_path: Path, digest: str) -> None:
    if payload.output_format != "glb":
        raise RuntimeError("The local ComfyUI Trellis2 workflow currently supports GLB output only")
    timeout = _comfy_timeout()
    base_url = _comfy_url()
    run_digest = f"{digest}-{uuid.uuid4().hex[:10]}"
    if payload.input_preprocessed:
        preparation = payload.image_preparation or {}
        requires_foreground = (preparation.get('assessment') or {}).get('background_kind') == 'complex'
        input_path = _confirmed_comfy_input(input_path, requires_foreground=requires_foreground,
                                            background_risk_accepted=preparation.get('background_risk_accepted') is True)
    else:
        input_path = _prepare_comfy_input(input_path)
    # ComfyUI is a local host bridge; never send it through a corporate or
    # Clash proxy configured for model/package downloads.
    with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        try:
            with input_path.open("rb") as source:
                upload = client.post(
                    f"{base_url}/upload/image",
                    files={"image": (f"source-{digest}.png", source, "image/png")},
                    data={"overwrite": "true"},
                )
            upload.raise_for_status()
            upload_data = upload.json()
            image_name = upload_data.get("name") if isinstance(upload_data, dict) else None
            if not isinstance(image_name, str) or not image_name:
                raise RuntimeError("ComfyUI upload did not return an input filename")

            response = client.post(
                f"{base_url}/prompt",
                json={"prompt": _build_comfy_prompt(image_name, run_digest, payload, has_transparency=True), "client_id": f"digital-human-{run_digest}"},
            )
            response.raise_for_status()
            prompt_data = response.json()
            prompt_id = prompt_data.get("prompt_id") if isinstance(prompt_data, dict) else None
            if not isinstance(prompt_id, str) or not prompt_id:
                raise RuntimeError("ComfyUI did not return a prompt_id")

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                history = client.get(f"{base_url}/history/{prompt_id}")
                if history.status_code == 200:
                    entry = history.json().get(prompt_id)
                    if isinstance(entry, dict):
                        status = entry.get("status") or {}
                        if status.get("status_str") == "error":
                            raise RuntimeError(_comfy_error_message(status))
                        if status.get("completed"):
                            file_info = _find_comfy_glb(entry.get("outputs"))
                            if file_info is not None:
                                _download_comfy_file(client, base_url, file_info, output_path)
                                return
                            # Some ComfyUI/custom-node versions mark an
                            # output-node execution successful but omit its
                            # return value from /history. The exporter still
                            # writes a uniquely prefixed GLB, so recover it
                            # from the read-only host output mount.
                            recovered = _find_local_comfy_glb(f"Trellis2Project-{run_digest}")
                            if recovered is not None:
                                shutil.copyfile(recovered, output_path)
                                return
                            raise RuntimeError("ComfyUI completed without a GLB output; check the ComfyUI console for node errors or CUDA OOM")
                time.sleep(_comfy_poll_interval())
            raise TimeoutError(f"ComfyUI prompt {prompt_id} did not complete within {timeout:g}s")
        except httpx.ConnectError as exc:
            raise RuntimeError('本机 3D 引擎连接失败，可能未启动或已经退出（ComfyUI）；'
                               '请先恢复引擎，本次不会自动重复提交生成。') from exc
        except httpx.RemoteProtocolError as exc:
            raise RuntimeError('本机 3D 引擎在生成期间断开连接，可能发生进程崩溃；'
                               '请检查 ComfyUI 日志和系统提交内存余量，本次不会自动重复提交生成。') from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"ComfyUI request failed at {base_url}: {exc}") from exc


def _comfy_error_message(status: Any) -> str:
    messages = status.get("messages") if isinstance(status, dict) else None
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, list) and len(message) > 1 and isinstance(message[1], dict):
                detail = message[1].get("exception_message")
                if detail:
                    return f"ComfyUI execution failed: {detail}"
    return "ComfyUI execution failed"


def _find_comfy_glb(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict):
        filename = value.get("filename") or value.get("name")
        if isinstance(filename, str) and filename.lower().endswith(".glb"):
            return {"filename": filename, "subfolder": str(value.get("subfolder") or ""), "type": str(value.get("type") or "output")}
        for nested in value.values():
            found = _find_comfy_glb(nested)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_comfy_glb(nested)
            if found:
                return found
    elif isinstance(value, str) and value.lower().endswith(".glb"):
        return {"filename": value, "subfolder": "", "type": "output"}
    return None


def _download_comfy_file(client: httpx.Client, base_url: str, file_info: dict[str, str], destination: Path) -> None:
    response = client.get(
        f"{base_url}/view",
        params={"filename": file_info["filename"], "subfolder": file_info.get("subfolder", ""), "type": file_info.get("type", "output")},
    )
    response.raise_for_status()
    if not response.content or response.content[:4] != b"glTF":
        raise RuntimeError("ComfyUI returned an invalid GLB artifact")
    destination.write_bytes(response.content)


def _find_local_comfy_glb(prefix: str) -> Path | None:
    root = _comfy_output_dir()
    if root is None:
        return None
    candidates = [path for path in root.rglob(f"{prefix}*.glb") if path.is_file() and path.stat().st_size > 0]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def _create_hf_client(space_id: str) -> Any:
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise RuntimeError("gradio_client is not installed; rebuild the trellis service") from exc
    token = os.getenv("HF_TOKEN", "").strip()
    return Client(space_id, hf_token=token or None)


def _hf_handle_file(path: Path) -> Any:
    try:
        from gradio_client import handle_file
    except ImportError as exc:
        raise RuntimeError("gradio_client is not installed; rebuild the trellis service") from exc
    return handle_file(str(path))


def _run_hf_space_inference(payload: GenerateRequest, input_path: Path, output_path: Path) -> None:
    if payload.output_format != "glb":
        raise RuntimeError("The temporary Microsoft TRELLIS.2 Space provider only supports GLB output")
    space_id = os.getenv("TRELLIS_HF_SPACE_ID", "microsoft/TRELLIS.2").strip() or "microsoft/TRELLIS.2"
    resolution = _hf_resolution(payload.texture_resolution)
    texture_size = _hf_texture_size(payload.texture_resolution)
    decimation_target = _hf_decimation_target(payload.mesh_density)
    client = _create_hf_client(space_id)
    logger.warning(
        "Using public Hugging Face TRELLIS.2 Space task_id=%s space=%s; uploaded image is sent to the remote demo",
        payload.task_id,
        space_id,
    )
    try:
        # The two public endpoints share Gradio session state. Do not split
        # them between clients or Extract GLB will not see the generated mesh.
        client.predict(
            _hf_handle_file(input_path),
            0,
            resolution,
            7.5, 0.7, 12, 5.0,
            7.5, 0.5, 12, 3.0,
            1.0, 0.0, 12, 3.0,
            api_name="/image_to_3d",
        )
        exported = client.predict(decimation_target, texture_size, api_name="/extract_glb")
        _save_hf_glb(exported, output_path)
    except Exception as exc:
        raise RuntimeError(f"Hugging Face TRELLIS.2 Space generation failed: {exc}") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _hf_resolution(value: str) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1024
    return "1536" if number >= 1536 else "1024" if number >= 1024 else "512"


def _hf_texture_size(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 2048
    return 4096 if number >= 4096 else 2048 if number >= 2048 else 1024


def _hf_decimation_target(value: str) -> int:
    return {"low": 150000, "medium": 300000, "high": 400000}.get(value, 300000)


def _walk_hf_result(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("path", "url"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                yield candidate
        for nested in value.values():
            yield from _walk_hf_result(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk_hf_result(nested)


def _save_hf_glb(exported: Any, destination: Path) -> None:
    """Persist a Gradio file result rather than retaining an expiring URL."""
    for candidate in _walk_hf_result(exported):
        if candidate.lower().split("?", 1)[0].endswith(".glb"):
            local = Path(candidate)
            if local.is_file():
                shutil.copyfile(local, destination)
            elif candidate.startswith(("http://", "https://")):
                with httpx.Client(timeout=_inference_timeout(), follow_redirects=True) as http:
                    response = http.get(candidate)
                    response.raise_for_status()
                    destination.write_bytes(response.content)
            else:
                continue
            if destination.is_file() and destination.stat().st_size > 0 and destination.read_bytes()[:4] == b"glTF":
                return
            destination.unlink(missing_ok=True)
    raise RuntimeError("Hugging Face TRELLIS.2 Space did not return a valid GLB artifact")


def _download_image(url: str, destination: Path) -> None:
    if not url or url.startswith(("upload://", "mock://")):
        raise RuntimeError("source image must be an accessible HTTP(S) URL")
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            if not response.content:
                raise RuntimeError("source image is empty")
            destination.write_bytes(response.content)
    except Exception as exc:
        raise RuntimeError(f"unable to download source image: {exc}") from exc


def _format_command(template: str, payload: GenerateRequest, input_path: Path, output_path: Path, job_id: str) -> list[str]:
    values = {"input_image": str(input_path), "output_file": str(output_path), "output_format": payload.output_format, "task_id": payload.task_id or "", "engine": payload.engine, "mode": payload.mode, "texture_resolution": payload.texture_resolution, "mesh_density": payload.mesh_density, "job_id": job_id}
    try:
        # The adapter runs in Linux containers, but keeping Windows paths
        # intact makes local runner tests and native development work too.
        return shlex.split(template.format(**values), posix=os.name != "nt")
    except KeyError as exc:
        raise RuntimeError(f"unknown TRELLIS_INFERENCE_COMMAND placeholder: {exc.args[0]}") from exc


def _inference_timeout() -> int:
    try:
        return max(30, int(os.getenv("TRELLIS_INFERENCE_TIMEOUT", "1800")))
    except ValueError:
        return 1800


@app.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest) -> GenerateResponse:
    try:
        result = run_inference(payload)
        logger.info("Generation accepted task_id=%s engine=%s job_id=%s", payload.task_id, payload.engine, result.job_id)
        return result
    except Exception as exc:
        logger.exception("Generation adapter failed task_id=%s engine=%s", payload.task_id, payload.engine)
        raise HTTPException(status_code=502, detail=f"3D generation failed: {str(exc)[:2000]}") from exc
