"""Restore normals from the original geometry without changing PBR textures or faces."""
import argparse
import json
import struct
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix, diags


def read_glb(path):
    data = path.read_bytes()
    size, kind = struct.unpack_from('<II', data, 12)
    assert data[:4] == b'glTF' and kind == 0x4E4F534A
    doc = json.loads(data[20:20 + size])
    bin_start = 20 + size
    bin_size, bin_kind = struct.unpack_from('<II', data, bin_start)
    assert bin_kind == 0x004E4942
    binary = data[bin_start + 8:bin_start + 8 + bin_size]

    def accessor(index):
        item = doc['accessors'][index]
        view = doc['bufferViews'][item['bufferView']]
        assert 'byteStride' not in view
        dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2'}[item['componentType']]
        width = {'VEC3': 3, 'VEC2': 2, 'SCALAR': 1}[item['type']]
        return np.frombuffer(binary, dtype=dtype, count=item['count'] * width,
                             offset=view.get('byteOffset', 0) + item.get('byteOffset', 0)).reshape(item['count'], width)

    return doc, binary, accessor


def main(original, textured, output, normal_smoothing=0):
    orig_doc, orig_bin, orig_acc = read_glb(original)
    orig_prim = orig_doc['meshes'][0]['primitives'][0]
    vertices = orig_acc(orig_prim['attributes']['POSITION'])
    faces = orig_acc(orig_prim['indices']).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    original_normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    if normal_smoothing:
        rows = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 1], faces[:, 2], faces[:, 0]])
        cols = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0], faces[:, 0], faces[:, 1], faces[:, 2]])
        adjacency = coo_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(vertices), len(vertices))).tocsr()
        degree = np.asarray(adjacency.sum(axis=1)).reshape(-1)
        adjacency = diags(1 / np.maximum(degree, 1)) @ adjacency
        for _ in range(normal_smoothing):
            original_normals = .5 * original_normals + .5 * (adjacency @ original_normals)
            length = np.linalg.norm(original_normals, axis=1)
            original_normals /= np.maximum(length[:, None], 1e-8)
    center = (vertices.min(0) + vertices.max(0)) / 2
    normalized = (vertices - center) * (.99999 / np.ptp(vertices, axis=0).max())

    doc, binary, acc = read_glb(textured)
    assert len(doc['meshes']) == 1 and len(doc['meshes'][0]['primitives']) == 1
    primitive = doc['meshes'][0]['primitives'][0]
    positions = acc(primitive['attributes']['POSITION'])
    distance, ids = cKDTree(normalized).query(positions, workers=4)
    assert distance.max() < 2e-7, float(distance.max())
    normals = original_normals[ids].copy()
    magnitude = np.linalg.norm(normals, axis=1)
    valid = magnitude > 1e-8
    normals[valid] /= magnitude[valid, None]
    normals[~valid] = (0, 1, 0)
    assert np.isfinite(normals).all()
    np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1, atol=2e-6)

    offset = (len(binary) + 3) & ~3
    payload = binary + b'\0' * (offset - len(binary)) + normals.astype('<f4').tobytes()
    view_index = len(doc['bufferViews'])
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': normals.nbytes, 'target': 34962})
    normal_index = len(doc['accessors'])
    doc['accessors'].append({'bufferView': view_index, 'componentType': 5126, 'count': len(normals), 'type': 'VEC3'})
    primitive['attributes']['NORMAL'] = normal_index
    doc['buffers'][0]['byteLength'] = len(payload)
    metadata = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    metadata += b' ' * ((-len(metadata)) % 4)
    total = 12 + 8 + len(metadata) + 8 + len(payload)
    result = struct.pack('<III', 0x46546C67, 2, total)
    result += struct.pack('<II', len(metadata), 0x4E4F534A) + metadata
    result += struct.pack('<II', len(payload), 0x004E4942) + payload
    output.write_bytes(result)

    out_doc, out_bin, out_acc = read_glb(output)
    # Byte-for-byte preservation of geometry, UVs, indices and embedded images.
    assert out_bin[:len(binary)] == binary
    assert out_doc['images'] == doc['images']
    np.testing.assert_array_equal(out_acc(normal_index), normals)
    print(json.dumps({'output': str(output), 'faces': len(acc(primitive['indices'])) // 3,
                      'vertices': len(normals), 'unchanged_existing_binary': True,
                      'max_mapping_error': float(distance.max()), 'normal_smoothing_passes': normal_smoothing,
                      'degenerate_normal_fallbacks': int((~valid).sum())}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('original', type=Path)
    parser.add_argument('textured', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--normal-smoothing', type=int, default=0)
    args = parser.parse_args()
    assert args.output.resolve() not in (args.original.resolve(), args.textured.resolve())
    main(args.original, args.textured, args.output, args.normal_smoothing)
