"""Read delivery statistics from the generated GLB instead of UI presets."""
import json
import struct


def glb_statistics(data: bytes) -> dict:
    if len(data) < 20 or data[:4] != b'glTF':
        raise ValueError('Invalid GLB header')
    version, length, json_length, kind = struct.unpack_from('<IIII', data, 4)
    if version != 2 or length != len(data) or kind != 0x4E4F534A or 20 + json_length > length:
        raise ValueError('Invalid GLB length or JSON chunk')
    document = json.loads(data[20:20 + json_length])
    accessors = document.get('accessors', [])
    positions, faces = set(), 0
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            position = primitive.get('attributes', {}).get('POSITION')
            if position is not None:
                positions.add(position)
            if primitive.get('mode', 4) == 4:
                index = primitive.get('indices', position)
                if index is not None:
                    faces += accessors[index]['count'] // 3
    return {'vertex_count': sum(accessors[index]['count'] for index in positions),
            'face_count': faces, 'file_size_mb': len(data) / (1024 * 1024)}
