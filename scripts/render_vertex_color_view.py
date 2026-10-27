"""Make a quick orthographic vertex-color diagnostic (not a beauty render)."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh


def main(source: Path, output: Path, axis: int, size: int) -> None:
    mesh = trimesh.load(source, force="mesh", process=False)
    vertices = np.asarray(mesh.vertices)
    colors = np.asarray(mesh.visual.vertex_colors)[:, :3]
    horizontal = 0
    vertical = 1 if axis == 2 else 2
    bounds = vertices[:, [horizontal, vertical]].min(0), vertices[:, [horizontal, vertical]].max(0)
    span = bounds[1] - bounds[0]
    x = np.clip(((vertices[:, horizontal] - bounds[0][0]) / span[0] * (size - 1)).astype(np.int32), 0, size - 1)
    y = np.clip(((bounds[1][1] - vertices[:, vertical]) / span[1] * (size - 1)).astype(np.int32), 0, size - 1)
    pixel = y * size + x
    order = np.argsort(vertices[:, axis], kind="stable")
    frame = np.full((size * size, 3), 32, dtype=np.uint8)
    frame[pixel[order]] = colors[order]
    Image.fromarray(frame.reshape(size, size, 3)).save(output)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--axis", type=int, choices=[1, 2], default=2)
    parser.add_argument("--size", type=int, default=768)
    args = parser.parse_args()
    main(args.source, args.output, args.axis, args.size)
