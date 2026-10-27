"""Extract embedded GLB textures and print simple image statistics."""

import argparse
import io
import json
import struct
from pathlib import Path

from PIL import Image, ImageStat


def extract(path: Path, output_dir: Path) -> None:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError(f"Not a GLB: {path}")
    offset = 12
    metadata = None
    binary = None
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8 : offset + 8 + length]
        if kind == 0x4E4F534A:
            metadata = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += length + 8
    if metadata is None or binary is None:
        raise ValueError(f"Missing GLB JSON or BIN chunk: {path}")

    for index, entry in enumerate(metadata.get("images", [])):
        view = metadata["bufferViews"][entry["bufferView"]]
        start = view.get("byteOffset", 0)
        payload = binary[start : start + view["byteLength"]]
        image = Image.open(io.BytesIO(payload))
        output = output_dir / f"{path.stem}_texture{index}.png"
        image.save(output)
        stats = ImageStat.Stat(image.convert("RGB"))
        print(f"{output} {image.size} mean={stats.mean} stddev={stats.stddev}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("glbs", nargs="+", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for glb in args.glbs:
        extract(glb, args.output_dir)
