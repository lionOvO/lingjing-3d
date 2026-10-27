"""Evidence-based failure advice; curated retrieval, no external LLM or GPU job."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db_session
from .models import GenerationTask, GenerationTaskStatus, Project
from .security import get_current_user

router = APIRouter(prefix="/api/v1/studio", tags=["failure diagnosis"])
KNOWLEDGE_FILE = Path(__file__).with_name("knowledge_data") / "generation_failures.json"


@lru_cache(maxsize=1)
def knowledge() -> dict[str, Any]:
    return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))


def classify_error(error: str) -> tuple[str, str, str]:
    """Match actual error clauses, not incidental advice appended by adapters."""
    text = error.lower()
    if "cancelled by user" in text or "canceled by user" in text:
        return "cancelled", "任务已由用户取消", "这条记录是主动取消，不作为引擎故障。"
    # Specific allocation failures outrank generic network wrappers.
    if any(x in text for x in ("cuda out of memory", "cuda error: out of memory", "allocation on device", "ran out of memory on your gpu", "torch.cuda.outofmemoryerror")):
        return "gpu_oom", "失败时发生显存分配错误", "错误记录明确指向 GPU 显存分配；是否仍然不足需结合当前状态判断。"
    # These wrappers contain suggestions mentioning memory, not memory evidence.
    if any(x in text for x in ("server disconnected", "remoteprotocolerror", "引擎在生成期间断开连接")):
        return "engine_disconnected", "生成期间引擎连接中断", "已确认通信中断，具体退出或崩溃原因尚未确认。"
    if any(x in text for x in ("connection refused", "connecterror", "引擎连接失败", "all connection attempts failed")):
        return "engine_unreachable", "失败时无法连接生成引擎", "已确认当时连接失败，尚不能推断是内存问题。"
    if any(x in text for x in ("memoryerror", "defaultcpuallocator", "not enough memory", "paging file", "页面文件太小", "分页文件太小", "系统提交内存不足", "commit headroom", "commit limit")):
        return "host_memory", "失败时发生系统内存分配错误", "错误指向 CPU 内存或系统提交额度，需查看失败时的资源记录确认细节。"
    if any(x in text for x in ("readtimeout", "timed out", "did not complete within", "timeoutexception", "执行超时")):
        return "timeout", "等待生成结果超时", "超时只表示等待结束，不能确认引擎任务已经停止。"
    if any(x in text for x in ("completed without a glb", "artifact missing", "模型保存失败", "generated model storage", "unable to save generated")):
        return "output_missing", "模型导出或保存未完成", "需要区分生成、导出和文件保存阶段。"
    if any(x in text for x in ("foreground", "透明通道", "复杂背景", "前景", "参考图确认")):
        return "input_preparation", "参考图需要重新确认", "输入检查未通过，应先核对主体完整性和背景。"
    if any(x in text for x in ("no such file", "filenotfounderror", "checkpoint not found", "model not found", "missing checkpoint", "工作流缺少", "does not exist", "node type not found", "not in list")):
        return "missing_resource", "资源或工作流配置不完整", "需要按实际报错定位文件、节点或参数，不宜直接重复生成。"
    return "unknown", "暂时无法确定失败原因", "现有错误不够具体，没有匹配到可直接适用的故障知识。"


def redact_error(error: str) -> str:
    text = str(error)[:12000]
    text = re.sub(r"(?:https?|redis|mysql(?:\+\w+)?|postgres(?:ql)?(?:\+\w+)?)://[^\s<>\"']+", "[服务地址已隐藏]", text, flags=re.I)
    text = re.sub(r"\bBearer\s+\S+", "Bearer [已隐藏]", text, flags=re.I)
    text = re.sub(r"(?i)(api[_-]?key|access[_-]?token|password|secret|authorization)[\"']?(\s*[=:]\s*)[\"']?[^\s,;\"'}]+", r"\1\2[已隐藏]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[密钥已隐藏]", text)
    return text[:3000]


def _number(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value < 2**60:
        return int(value)
    return None


async def probe_runtime() -> dict[str, Any]:
    """Read only the internal adapter; never fetch addresses from task text."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(7, connect=2), trust_env=False) as client:
            response = await client.get(f"{settings.trellis_url.rstrip('/')}/diagnostics")
            if response.status_code == 404 and settings.diagnostics_comfy_url:
                # The old adapter can be serving a long generation request.
                # Read the explicitly configured local bridge without restarting
                # that adapter or guessing an address from task text.
                return await probe_local_bridge()
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("invalid diagnostic response")
        # Whitelist even an unexpected adapter response, never forward raw logs.
        return {
            "adapter": "online", "engine": data.get("engine") if data.get("engine") in ("online", "offline", "unknown", "not_applicable") else "unknown",
            "queue_running": _number(data.get("queue_running")), "queue_pending": _number(data.get("queue_pending")),
            "ram_total": _number(data.get("ram_total")), "ram_free": _number(data.get("ram_free")),
            "vram_total": _number(data.get("vram_total")), "vram_free": _number(data.get("vram_free")),
            "workflow_ready": data.get("workflow_ready") if isinstance(data.get("workflow_ready"), bool) else None,
            "workflow_fingerprint": str(data.get("workflow_fingerprint", ""))[:16] if re.fullmatch(r"[0-9a-f]{16,64}", str(data.get("workflow_fingerprint", ""))) else None,
        }
    except (httpx.HTTPError, ValueError, TypeError):
        return {"adapter": "unavailable", "engine": "unknown"}


async def probe_local_bridge() -> dict[str, Any]:
    result: dict[str, Any] = {"adapter": "online", "engine": "unknown", "probe_source": "configured_local_bridge"}
    base = settings.diagnostics_comfy_url.rstrip('/')
    async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
        try:
            response = await client.get(f"{base}/system_stats")
            response.raise_for_status()
            data = response.json()
            system = data.get('system')
            if not isinstance(system, dict):
                raise ValueError('invalid system stats')
            result.update(engine='online', ram_total=_number(system.get('ram_total')), ram_free=_number(system.get('ram_free')))
            devices = data.get('devices') or []
            device = next((d for d in devices if isinstance(d, dict) and d.get('type') == 'cuda'), {})
            result.update(vram_total=_number(device.get('vram_total')), vram_free=_number(device.get('vram_free')))
        except httpx.ConnectError:
            result['engine'] = 'offline'
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        try:
            response = await client.get(f"{base}/queue")
            response.raise_for_status()
            data = response.json()
            for name in ('running', 'pending'):
                rows = data.get(f'queue_{name}')
                if isinstance(rows, list):
                    result[f'queue_{name}'] = len(rows)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
    return result


def retrieve_knowledge(code: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    # Only this project's verified local workflow is covered at present.
    engine = params.get("engine")
    provider = params.get("provider")
    if (engine and engine != "trellis2") or (provider and provider != "local_comfyui"):
        return []
    return [entry for entry in knowledge()["entries"] if code in entry["codes"]]


def build_report(task: GenerationTask, runtime: dict[str, Any], related: list[dict[str, Any]]) -> dict[str, Any]:
    params = task.generation_params or {}
    code, title, summary = classify_error(task.error_message or "")
    hits = retrieve_knowledge(code, params)
    actions = list(dict.fromkeys(action for hit in hits for action in hit["actions"]))
    if not actions and code != "cancelled":
        actions = ["保留本次参数，按失败时间查看引擎日志中的具体异常和节点。", "导出本页诊断记录，补充失败时的日志后再决定是否重试。"]
    evidence = [{"scope": "failure", "label": "任务保存的错误", "value": redact_error(task.error_message or "未保存详细错误")}]
    adapter = runtime.get("adapter")
    engine = runtime.get("engine")
    evidence.append({"scope": "current", "label": "生成服务", "value": "可连接" if adapter == "online" else "该提供方不适用本机检测" if adapter == "not_probed" else "诊断接口不可用，当前状态未知"})
    evidence.append({"scope": "current", "label": "ComfyUI", "value": {"online": "当前在线；不代表上次任务成功", "offline": "当前无法连接", "not_applicable": "当前提供方不适用本机检测"}.get(engine, "未知")})
    running, pending = runtime.get("queue_running"), runtime.get("queue_pending")
    if running is not None and pending is not None:
        evidence.append({"scope": "current", "label": "引擎总队列", "value": f"运行 {running}，等待 {pending}；计数不能识别本任务"})
    for key, label in (("ram_free", "主机可用物理内存"), ("vram_free", "可用显存")):
        if runtime.get(key) is not None:
            evidence.append({"scope": "current", "label": label, "value": f"{runtime[key] / 1024**3:.2f} GiB；仅为当前值"})
    if runtime.get("workflow_ready") is not None:
        evidence.append({"scope": "current", "label": "工作流配置", "value": "必要节点存在，不代表所有权重和补丁已验证" if runtime["workflow_ready"] else "配置检查未通过"})
    if engine == "offline":
        actions.insert(0, "当前引擎仍无法连接：先恢复引擎并重新检测，再考虑重新生成。")
    elif engine == "online" and code == "engine_unreachable" and hits:
        actions[0] = "当前引擎已经恢复连接，无需仅因这条历史错误重启；确认原任务未运行后，可手动重新生成。"
    if (runtime.get('queue_running') or 0) + (runtime.get('queue_pending') or 0) > 0:
        actions.insert(0, "当前引擎仍有任务：先核对 ComfyUI 队列，不要为处理旧错误重启引擎或重复提交。")
    unknowns = ["未采集失败瞬间的资源峰值。", "本次检测不提供 Windows 已提交内存上限、分页文件及磁盘容量。", "未读取宿主机控制台日志；仅使用本任务保存的错误记录。"]
    if not hits and code not in ("cancelled", "unknown"):
        unknowns.append("当前知识库没有适用于该引擎或提供方的案例。")
    if not params.get('provider'):
        unknowns.append("历史任务未记录实际提供方；本机知识仅作候选，需核对当时使用的工作流。")
    return {
        "task_id": task.id, "task_status": task.status.value,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "classification": {"code": code, "title": title, "summary": summary, "certainty": "待补充证据" if code == "unknown" else "错误类型已识别，根因需核对"},
        "parameters": {key: params[key] for key in ("engine", "provider", "generation_mode", "texture_resolution", "mesh_density", "pbr_enabled", "seed") if key in params and isinstance(params[key], (str, int, float, bool))},
        "runtime": runtime, "evidence": evidence, "actions": actions,
        "knowledge": hits, "knowledge_version": knowledge()["version"],
        "retrieval": {"method": "error_code_and_workflow_filter", "hits": len(hits), "external_model_used": False},
        "related_failures": related, "limitations": unknowns,
        "retry_advice": "你可以手动重新生成；请先核对队列，避免重复执行。",
    }


@router.get("/diagnosis/knowledge")
async def diagnosis_knowledge(user=Depends(get_current_user)):
    return knowledge()


@router.get("/tasks/{task_id}/diagnosis")
async def diagnose_task(task_id: int, response: Response, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    # Asset helpers only accept completed tasks; failure diagnostics must use
    # its own ownership query and must reject before any infrastructure probe.
    row = (await db.execute(select(GenerationTask, Project).join(Project).where(GenerationTask.id == task_id, Project.user_id == user.id))).first()
    if not row:
        raise HTTPException(404, "任务不存在")
    task, _ = row
    if task.status != GenerationTaskStatus.FAILED:
        raise HTTPException(409, "仅失败任务需要故障诊断；当前任务状态已变化，请刷新页面")
    failure_signature = (task.error_message, task.retry_count, task.celery_task_id)
    code = classify_error(task.error_message or "")[0]
    candidates = (await db.scalars(select(GenerationTask).join(Project).where(Project.user_id == user.id, GenerationTask.status == GenerationTaskStatus.FAILED, GenerationTask.id != task.id).order_by(GenerationTask.id.desc()).limit(40))).all()
    params = task.generation_params or {}
    related = [{"task_id": other.id, "created_at": other.created_at.isoformat(), "label": "同类错误记录，不代表同一根因或已有有效修复"} for other in candidates if code not in ("unknown", "cancelled") and classify_error(other.error_message or "")[0] == code and (other.generation_params or {}).get("engine") == params.get("engine") and (other.generation_params or {}).get("provider") == params.get("provider")][:3]
    runtime = await probe_runtime() if params.get('provider') in (None, 'local_comfyui') else {'adapter': 'not_probed', 'engine': 'not_applicable'}
    # Recheck after network I/O so a concurrent retry does not return stale
    # failure advice as a diagnosis of an actively running attempt.
    # End the read snapshot as MySQL REPEATABLE READ would otherwise hide a
    # worker's concurrent retry even from an explicit refresh.
    await db.rollback()
    await db.refresh(task)
    if task.status != GenerationTaskStatus.FAILED or (task.error_message, task.retry_count, task.celery_task_id) != failure_signature:
        raise HTTPException(409, "任务状态已变化，请刷新后重新检测")
    response.headers["Cache-Control"] = "private, no-store"
    return build_report(task, runtime, related)
