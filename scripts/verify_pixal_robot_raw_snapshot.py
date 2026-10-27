"""Compare current robot geometry with the preserved pre-failure neural export."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
raw=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output\PixalRound3_Robot_RawCached_20261009_00001_.glb')
current=json.loads((ROOT/'tmp/pixal-round3-sparse-resume-robot-prediction-20261011.json').read_text())
with raw.open('rb') as fp:
    magic,version,total=struct.unpack('<4sII',fp.read(12))
    assert magic==b'glTF' and version==2 and total==raw.stat().st_size
    length,kind=struct.unpack('<II',fp.read(8));assert kind==0x4E4F534A
    document=json.loads(fp.read(length))
    binary_length,kind=struct.unpack('<II',fp.read(8));assert kind==0x004E4942
    binary_offset=fp.tell()
    primitive=document['meshes'][0]['primitives'][0]
    results={}
    for name,index,width,component_type in [('vertices',primitive['attributes']['POSITION'],3,5126),('faces',primitive['indices'],1,5125)]:
        accessor=document['accessors'][index]
        assert accessor['componentType']==component_type
        view=document['bufferViews'][accessor['bufferView']]
        assert view.get('byteStride',width*4)==width*4
        offset=binary_offset+view.get('byteOffset',0)+accessor.get('byteOffset',0)
        count=accessor['count'];remaining=count*width*4
        fp.seek(offset);digest=hashlib.sha256()
        while remaining:
            chunk=fp.read(min(8*1024*1024,remaining));assert chunk
            digest.update(chunk);remaining-=len(chunk)
        shape=[count,3] if name=='vertices' else [count//3,3]
        sha=digest.hexdigest()
        results[name]=dict(before_sha256=sha,after=current[name],same_shape=shape==current[name]['shape'],same_bytes=sha==current[name]['sha256'])
out=ROOT/'tmp/pixal-robot-neural-geometry-comparison-20261011.json'
assert not out.exists(),'Preserve previous comparison'
out.write_text(json.dumps(dict(source=str(raw),scope='Geometry only; old neural texture volume was not preserved',arrays=results),indent=2))
print(json.dumps({name:row['same_shape'] and row['same_bytes'] for name,row in results.items()}))
