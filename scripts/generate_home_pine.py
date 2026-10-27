"""Generate one homepage pine using the user's local Pixal3D engine.

This creates an isolated asset prompt; it never edits the platform workflow.
Re-run with --status to inspect the recorded prompt instead of submitting again.
"""
import argparse
import json
import shutil
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp' / 'home-pine-20261027'
BASE = 'http://127.0.0.1:8188'
SESSION = requests.Session()
SESSION.trust_env = False


def build_workflow(image_name: str) -> dict:
    """Rebuild the decoder's flexible dual grid before simplifying its surface."""
    workflow = json.loads((ROOT / 'services/trellis/workflow_6gb.json').read_text(encoding='utf-8'))
    workflow['6']['inputs']['image'] = image_name
    workflow['55']['inputs'].update(remove_background=False, padding=12)
    workflow['45']['inputs'].update(pipeline_type='512', generate_texture_slat=False, seed=20261027, max_num_tokens=24576, max_views=1)
    workflow['75'] = {'class_type': 'Trellis2ReconstructMeshWithQuad_GGUF', 'inputs': {
        'mesh': ['45', 0], 'remesh_band': 1.0, 'resolution': '512',
        'remove_floaters': False, 'remove_inner_faces': False,
    }}
    # The attrs=None branch in node 54 only converts coordinates; its remesh
    # checkbox is ignored. Reconstruction therefore needs its own explicit node.
    workflow['54']['inputs'].update(mesh=['75', 0], texture_size=1024, target_face_num=180000, remesh=False, dual_contouring_resolution='512', remove_floaters=False)
    workflow['70'] = {'class_type': 'Trellis2SimplifyTrimesh_GGUF', 'inputs': {'trimesh': ['54', 0], 'target_face_num': 180000, 'method': 'Cumesh'}}
    workflow['71'] = {'class_type': 'Trellis2MeshTexturing_GGUF', 'inputs': {
        'pipeline': ['39', 0], 'image': ['55', 0], 'trimesh': ['70', 0],
        'seed': 20261027, 'texture_steps': 20, 'texture_guidance_strength': 3.0,
        'texture_guidance_rescale': 0.2, 'texture_rescale_t': 3.0,
        'resolution': '1024', 'texture_size': 1024, 'texture_alpha_mode': 'OPAQUE',
        'double_side_material': False, 'texture_guidance_interval_start': 0.0,
        'texture_guidance_interval_end': 0.9, 'max_views': 1, 'bake_on_vertices': False,
        'use_custom_normals': False, 'uv_unwrap_method': 'Smart',
        'mesh_cluster_threshold_cone_half_angle_rad': 60.0,
        'use_tiled_encoder': True, 'encoder_tile_size': 512, 'encoder_overlap': 24,
        'use_tiled_decoder_for_texture': True, 'decoder_tile_size': 120,
        'decoder_overlap': 48, 'sampler': 'euler',
    }}
    workflow['19']['inputs'].update(trimesh=['71', 0], filename_prefix='HomePineReconstructed20261027')
    workflow['20'] = {'class_type': 'Trellis2ExportMesh_GGUF', 'inputs': {'trimesh': ['70', 0], 'filename_prefix': 'HomePineReconstructedGeometry20261027', 'file_format': 'glb'}}
    return workflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    record = OUT / 'submission.json'
    if args.status:
        info = json.loads(record.read_text(encoding='utf-8'))
        history = SESSION.get(BASE + '/history/' + info['prompt_id'], timeout=20).json()
        (OUT / 'history.json').write_text(json.dumps(history, indent=2), encoding='utf-8')
        item = history.get(info['prompt_id'])
        if item:
            status = item.get('status', {})
            errors = [v.get('exception_message', '') for k, v in status.get('messages', []) if k == 'execution_error']
            print(json.dumps({'status': status.get('status_str'), 'completed': status.get('completed'), 'errors': errors}, ensure_ascii=False))
            print(json.dumps(item.get('outputs', {}).get('19', {}), ensure_ascii=False))
        else:
            queue = SESSION.get(BASE + '/queue', timeout=10).json()
            print(json.dumps({key: [entry[1] for entry in value] for key, value in queue.items()}))
        return
    if record.exists():
        previous = json.loads(record.read_text(encoding='utf-8'))
        history = SESSION.get(BASE + '/history/' + previous['prompt_id'], timeout=20).json()
        status = history.get(previous['prompt_id'], {}).get('status', {})
        if not args.retry_failed or status.get('status_str') != 'error':
            raise RuntimeError('A submission exists and is not a confirmed failed retry.')
        (OUT / ('failed-' + previous['prompt_id'] + '.json')).write_text(json.dumps(history, indent=2), encoding='utf-8')
    queue = SESSION.get(BASE + '/queue', timeout=10).json()
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('The engine is busy; no asset generation was submitted.')
    source = OUT / 'pine-reference.png'
    shutil.copy2(args.source, source)
    from PIL import Image
    with Image.open(source) as im:
        if im.mode != 'RGBA' or im.getchannel('A').getextrema()[0] == 255:
            raise RuntimeError('Reference must contain a real alpha background.')
    with source.open('rb') as file:
        response = SESSION.post(BASE + '/upload/image', files={'image': ('home-pine-20261027.png', file, 'image/png')}, timeout=30)
    response.raise_for_status()
    uploaded = response.json()
    workflow = build_workflow('/'.join(filter(None, [uploaded.get('subfolder'), uploaded['name']])))
    (OUT / 'prompt.json').write_text(json.dumps(workflow, indent=2), encoding='utf-8')
    response = SESSION.post(BASE + '/prompt', json={'prompt': workflow, 'client_id': 'lingjing-home-pine-20261027'}, timeout=30)
    response.raise_for_status()
    result = response.json()
    if result.get('node_errors') or not result.get('prompt_id'):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    record.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
