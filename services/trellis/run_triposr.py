"""Container runner adapting TripoSR's directory output to one GLB file."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import trimesh


def convert_baked_obj_to_glb(mesh_path: Path, texture_path: Path, output_path: Path) -> None:
    """Package TripoSR's textured OBJ output as a standards-compliant GLB.

    TripoSR calls ``xatlas.export`` whenever texture baking is enabled. That
    function always writes an OBJ, even when the requested filename ends in
    ``.glb``. Supplying a material file before loading makes trimesh embed the
    baked PNG texture into the binary GLB.
    """
    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise RuntimeError(f"TripoSR did not produce {mesh_path}")
    if not texture_path.is_file() or texture_path.stat().st_size == 0:
        raise RuntimeError(f"TripoSR did not produce {texture_path}")

    material_path = mesh_path.with_suffix(".mtl")
    material_path.write_text("newmtl baked_material\nmap_Kd texture.png\n", encoding="ascii")
    obj_text = mesh_path.read_text(encoding="utf-8")
    if "mtllib " not in obj_text:
        mesh_path.write_text(f"mtllib {material_path.name}\nusemtl baked_material\n{obj_text}", encoding="utf-8")

    scene = trimesh.load(mesh_path, force="scene", process=False)
    glb = scene.export(file_type="glb")
    if not isinstance(glb, bytes) or glb[:4] != b"glTF":
        raise RuntimeError("OBJ to GLB conversion produced an invalid GLB payload")
    output_path.write_bytes(glb)
    if output_path.read_bytes()[:4] != b"glTF":
        raise RuntimeError(f"GLB validation failed for {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--texture-resolution", default="2048")
    args = parser.parse_args()

    # Texture baking needs an OpenGL context. Docker Desktop provides CUDA
    # compute but not an NVIDIA EGL device, so it runs in an Xvfb display with
    # Mesa's llvmpipe software renderer.
    output_file = Path(args.output).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="triposr-") as temp_dir:
        command = [
            "xvfb-run",
            "--auto-servernum",
            "--server-args=-screen 0 1280x1024x24",
            sys.executable,
            "/models/triposr/run.py",
            args.input,
            "--device",
            "cuda:0",
            "--pretrained-model-name-or-path",
            args.model,
            "--output-dir",
            temp_dir,
            "--model-save-format",
            "obj",
            "--bake-texture",
            "--texture-resolution",
            str(args.texture_resolution),
        ]
        completed = subprocess.run(command, text=True)
        if completed.returncode != 0:
            return completed.returncode
        generated_dir = Path(temp_dir) / "0"
        convert_baked_obj_to_glb(
            generated_dir / "mesh.obj",
            generated_dir / "texture.png",
            output_file,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
