"""Validate completed benchmark GLBs and record structural metrics."""
import argparse
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

OUTPUT = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output')
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('manifest', type=Path)
parser.add_argument('--output', type=Path, default=ROOT / 'tmp/pixal-generation-cascade-metrics-20261009.json')
parser.add_argument('--allow-pending', action='store_true')
parser.add_argument('--export-node', default='19', help='Exporter to audit; 20 is the no-remesh comparison.')
args = parser.parse_args()
results = []
for job in json.loads(args.manifest.read_text(encoding='utf-8')):
    replay = job.get('kind') == 'checkpoint_replay'
    history = None
    if not replay:
        history_path = Path(job['history_path']) if 'history_path' in job else ROOT / f"tmp/PixalPipeline_{Path(job['image']).stem}_{job['label']}_history.json"
        if not history_path.is_file() and args.allow_pending:
            continue
        history = json.loads(history_path.read_text(encoding='utf-8'))
        if not history.get('status', {}).get('completed'):
            if args.allow_pending:
                continue
            raise RuntimeError(f"Not completed: {job['image']}")
    prompt = json.loads(Path(job['workflow']).read_text(encoding='utf-8'))
    if replay:
        path = Path(job['model'])
    else:
        paths = list(OUTPUT.glob(prompt[args.export_node]['inputs']['filename_prefix'] + '*.glb'))
        path = max(paths, key=lambda p: p.stat().st_mtime_ns)
    data = path.read_bytes()
    magic, version, total = struct.unpack_from('<4sII', data)
    assert magic == b'glTF' and version == 2 and total == len(data)
    offset = 12
    document = binary = None
    while offset < len(data):
        length, kind = struct.unpack_from('<II', data, offset)
        chunk = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += length + 8
    assert document is not None and binary is not None

    def accessor(index):
        info = document['accessors'][index]
        view = document['bufferViews'][info['bufferView']]
        dtype = np.dtype({5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[info['componentType']])
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[info['type']]
        start = view.get('byteOffset', 0) + info.get('byteOffset', 0)
        stride = view.get('byteStride', dtype.itemsize * width)
        return np.ndarray((info['count'], width), dtype=dtype, buffer=binary, offset=start,
                          strides=(stride, dtype.itemsize))

    primitives = [p for m in document['meshes'] for p in m['primitives']]
    assert len(primitives) == 1
    primitive = primitives[0]
    assert primitive.get('mode', 4) == 4
    positions = accessor(primitive['attributes']['POSITION'])
    uv = accessor(primitive['attributes']['TEXCOORD_0'])
    indices = accessor(primitive['indices']).reshape(-1)
    assert np.isfinite(positions).all() and np.isfinite(uv).all()
    assert len(uv) == len(positions) and len(indices) % 3 == 0
    assert indices.max() < len(positions)
    assert uv.min() >= -1e-6 and uv.max() <= 1.000001
    material = document['materials'][primitive['material']]['pbrMetallicRoughness']
    image_sizes = []
    for key in ('baseColorTexture', 'metallicRoughnessTexture'):
        texture = document['textures'][material[key]['index']]
        view = document['bufferViews'][document['images'][texture['source']]['bufferView']]
        start = view.get('byteOffset', 0)
        image = Image.open(io.BytesIO(binary[start:start + view['byteLength']]))
        image.load()
        size = prompt['54']['inputs']['texture_size']
        assert image.size == (size, size)
        image_sizes.append(list(image.size))
    seconds = None
    if history:
        messages = history['status']['messages']
        start_time = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_start')
        end_time = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_success')
        seconds = (end_time - start_time) / 1000
    row = dict(image=job['image'], prompt_id=job['prompt_id'], label=job['label'],
               export_node=job.get('export_node', args.export_node), model=str(path),
               kind=job.get('kind', 'comfy_completed'),
               file_bytes=len(data), vertices=len(positions), faces=len(indices) // 3,
               bounds=[positions.min(0).tolist(), positions.max(0).tolist()],
               texture_sizes=image_sizes, normals='NORMAL' in primitive['attributes'],
               execution_seconds=seconds)
    results.append(row)
    print(json.dumps(row, ensure_ascii=False))
args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
