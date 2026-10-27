"""Conservative static GLB inspection/repair, preserving scene nodes and UV seams."""
import hashlib
import io
import json
import struct

import numpy as np
import trimesh

MAX_BYTES = 80 * 1024 * 1024
MAX_FACES = 2_000_000


def read_scene(data, *, repair=False):
    if len(data) > MAX_BYTES or len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("仅支持 80MB 以内的 GLB 模型")
    version, length, size, kind = struct.unpack_from("<IIII", data, 4)
    if version != 2 or length != len(data) or kind != 0x4E4F534A or size + 20 > length:
        raise ValueError("GLB 文件结构无效")
    document = json.loads(data[20:20+size])
    if any(row.get("uri") and not row["uri"].startswith("data:") for group in ("buffers", "images") for row in document.get(group, [])):
        raise ValueError("请先将外部贴图和缓冲区打包进 GLB")
    if repair and (document.get("skins") or document.get("animations") or any(p.get("targets") for m in document.get("meshes", []) for p in m.get("primitives", []))):
        raise ValueError("自动修复仅支持静态模型，避免丢失骨骼、动画或形态键")
    accessors = document.get("accessors", [])
    count = sum(accessors[p.get("indices", p.get("attributes", {}).get("POSITION", 0))].get("count", 0)//3 for m in document.get("meshes", []) for p in m.get("primitives", []))
    if count > MAX_FACES:
        raise ValueError("模型超过 200 万面，请先在建模软件中减面")
    scene = trimesh.load(io.BytesIO(data), file_type="glb", force="scene", process=False)
    if not scene.geometry or any(not isinstance(mesh, trimesh.Trimesh) for mesh in scene.geometry.values()):
        raise ValueError("模型没有可检查的三角网格")
    if any(not np.isfinite(mesh.vertices).all() for mesh in scene.geometry.values()):
        raise ValueError("模型含无效坐标，请先在建模软件中修正")
    return scene


def summarize(scene, data):
    rows = []
    for name, mesh in scene.geometry.items():
        # Weld only the diagnostic copy: UV seams must not look like holes.
        topo = mesh.copy()
        topo.merge_vertices(merge_tex=True, merge_norm=True)
        edges = np.bincount(topo.edges_unique_inverse, minlength=len(topo.edges_unique))
        uv = getattr(mesh.visual, "uv", None)
        rows.append({"name": name, "vertices": len(mesh.vertices), "faces": len(mesh.faces),
                     "degenerate_faces": int((~mesh.nondegenerate_faces()).sum()),
                     "duplicate_faces": int((~mesh.unique_faces()).sum()),
                     "boundary_edges": int((edges == 1).sum()), "nonmanifold_edges": int((edges > 2).sum()),
                     "watertight": bool(topo.is_watertight), "winding_consistent": bool(topo.is_winding_consistent),
                     "has_uv": uv is not None, "uv_valid": bool(uv is not None and len(uv) == len(mesh.vertices) and np.isfinite(uv).all()),
                     "material": getattr(getattr(mesh.visual, "material", None), "name", None) or "默认材质"})
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_mb": round(len(data)/1024/1024, 3),
            "faces": sum(r["faces"] for r in rows), "vertices": sum(r["vertices"] for r in rows),
            "meshes": rows, "note": "边界和水密性按合并同位置顶点后的副本检查；开放衣物并不一定需要封孔。结构检查不代表外观相似度。"}


def inspect_glb(data):
    return summarize(read_scene(data), data)


def repair_glb(data, options):
    scene = read_scene(data, repair=True)
    before = summarize(scene, data)
    warnings = []
    for name, mesh in scene.geometry.items():
        if options["clean_faces"]:
            mesh.update_faces(mesh.nondegenerate_faces())
            mesh.update_faces(mesh.unique_faces())
            mesh.remove_unreferenced_vertices()
        if not len(mesh.faces):
            raise ValueError("清理会移除全部网格，已取消修复")
        if options["fix_winding"]:
            trimesh.repair.fix_winding(mesh)
        if options["fill_holes"]:
            if getattr(mesh.visual, "uv", None) is not None:
                warnings.append(f"{name} 含 UV，跳过封孔以保留贴图；请在建模软件中处理大孔或贴图区域。")
            else:
                trimesh.repair.fill_holes(mesh)
    result = scene.export(file_type="glb")
    after = inspect_glb(result)
    if sum(row["has_uv"] for row in after["meshes"]) < sum(row["has_uv"] for row in before["meshes"]):
        raise ValueError("贴图坐标未完整保留，已取消保存")
    return result, {"before": before, "after": after, "warnings": warnings}
