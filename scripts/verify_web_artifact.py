"""Download and inspect an actual completed web task; never submit inference."""
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
from urllib.request import ProxyHandler, build_opener

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/high-quality-integration'
HTTP = build_opener(ProxyHandler({}))


def get(path):
    with HTTP.open('http://127.0.0.1:8080' + path, timeout=60) as response:
        return response.read(), {key.lower(): value for key, value in response.headers.items()}


def main(task_id):
    raw, _ = get(f'/api/v1/tasks/{task_id}')
    task = json.loads(raw)
    assert task['status'] == 'completed', task['status']
    assert task['generation_params'].get('provider') == 'local_comfyui'
    assert task['output_model_url'] == f'/api/v1/models/{task_id}/content'
    data, headers = get(task['output_model_url'] + '?download=true')
    assert data[:4] == b'glTF' and struct.unpack_from('<I', data, 8)[0] == len(data)
    destination = OUTPUT / f'web-task-{task_id}.glb'
    destination.write_bytes(data)
    json_length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    binary = data[28 + json_length:]
    primitives = [p for m in document['meshes'] for p in m['primitives']]
    assert primitives and all('TEXCOORD_0' in p['attributes'] for p in primitives)
    uv_ranges = []
    for primitive in primitives:
        accessor = document['accessors'][primitive['attributes']['TEXCOORD_0']]
        assert accessor['componentType'] == 5126 and accessor['type'] == 'VEC2'
        view = document['bufferViews'][accessor['bufferView']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        stride = view.get('byteStride', 8)
        uv = [struct.unpack_from('<ff', binary, offset + index * stride) for index in range(accessor['count'])]
        assert all(math.isfinite(value) for pair in uv for value in pair)
        bounds = [(min(pair[axis] for pair in uv), max(pair[axis] for pair in uv)) for axis in (0, 1)]
        assert all(high - low > 0.5 for low, high in bounds)
        uv_ranges.append(bounds)
    vertices = sum(document['accessors'][p['attributes']['POSITION']]['count'] for p in primitives)
    faces = sum(document['accessors'][p['indices']]['count'] // 3 for p in primitives)
    assert vertices > 10000 and faces > 10000
    materials = document['materials']
    assert any('baseColorTexture' in m.get('pbrMetallicRoughness', {}) and
               'metallicRoughnessTexture' in m.get('pbrMetallicRoughness', {}) for m in materials)
    images = []
    for index, entry in enumerate(document['images']):
        view = document['bufferViews'][entry['bufferView']]
        image_data = binary[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']]
        with Image.open(io.BytesIO(image_data)) as image:
            image.load()
            images.append(dict(index=index, size=image.size, mode=image.mode,
                               stddev=ImageStat.Stat(image.convert('RGB')).stddev))
            image.save(OUTPUT / f'web-task-{task_id}-texture-{index}.png')
    assert images and all(item['size'] == (1024, 1024) for item in images)
    assert any(max(item['stddev']) > 10 for item in images)
    report = dict(task_id=task_id, status=task['status'], project_id=task['project_id'],
                  generation_params=task['generation_params'], retry_count=task['retry_count'],
                  quality_score=task['quality_score'], quality_checks=(task.get('retrieved_params') or {}).get('quality_checks'),
                  bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), vertices=vertices, faces=faces,
                  images=images, materials=materials, has_uv=True, uv_ranges=uv_ranges,
                  content_type=headers.get('content-type'), content_disposition=headers.get('content-disposition'),
                  created_at=task.get('created_at'), completed_at=task.get('completed_at'), model_path=str(destination))
    (OUTPUT / f'web-task-{task_id}-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('task_id', 'status', 'retry_count', 'quality_score', 'bytes', 'vertices', 'faces', 'has_uv', 'images', 'content_disposition')}, ensure_ascii=False))


if __name__ == '__main__':
    main(int(sys.argv[1]))
