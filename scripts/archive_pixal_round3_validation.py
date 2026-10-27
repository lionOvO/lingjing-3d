"""Archive completed three-category validation with source and cache provenance."""
import hashlib
import json
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
parser=argparse.ArgumentParser()
parser.add_argument('--label-prefix',default='20261011-round3-sparse-resume')
parser.add_argument('--metrics-prefix',default='pixal-full-round3-sparse-resume')
parser.add_argument('--output',type=Path,default=ROOT/'tmp/pixal-round3-final-validation-20261011.json')
args=parser.parse_args()
prefix=args.label_prefix
records=[];pids=set();hashes=[];settings=[]
for category in ('person','robot','helmet'):
 label=f'{prefix}-{category}'
 job=json.loads((ROOT/f'tmp/pixal-full-{label}-manifest.json').read_text(encoding='utf-8'))[0]
 metric=json.loads((ROOT/f'tmp/{args.metrics_prefix}-{category}-metrics.json').read_text(encoding='utf-8'))[0]
 quality=json.loads((ROOT/f'tmp/{args.metrics_prefix}-{category}-quality.json').read_text(encoding='utf-8'))
 graph=json.loads(Path(job['workflow']).read_text(encoding='utf-8'))
 assert job['status']['status_str']=='success' and job['status']['completed']
 cached=[m[1]['nodes'] for m in job['status']['messages'] if m[0]=='execution_cached']
 assert not {'45','54','19'} & {n for group in cached for n in group},'Generation/postprocess/export must execute'
 assert Path(metric['model']).is_file()
 assert quality['model']==metric['model']
 assert quality['zero_area_faces']==0 and quality['same_winding_duplicate_faces']==0 and quality['finite_vertices']
 for name,expected in job['source_sha256'].items():
  path=Path(name) if Path(name).is_absolute() else PLUGIN/name
  if path.parent.name=='Pixal3DValidationSnapshot' and not path.exists():
   path=path.parent.with_name('Pixal3DValidationSnapshot.disabled')/path.name
  assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,(category,name)
 common={key:dict(graph[key]['inputs']) for key in ('39','45','54')}
 seed=common['45'].pop('seed')
 face_target=common['54'].pop('target_face_num')
 pids.add(job['pid']);hashes.append(job['source_sha256']);settings.append(common)
 assert metric['prompt_id']==job['prompt_id']
 records.append(dict(metric,category=category,pid=job['pid'],cached=cached,
                     peak_bytes=job['peak_bytes'],generation_seed=seed,target_face_num=face_target,quality=quality))
assert len(pids)==1,'Same-process continuity required'
assert all(h==hashes[0] for h in hashes),'Source versions differ'
assert all(s==settings[0] for s in settings),'Common model/generation/postprocess parameters differ'
result=dict(version=prefix,same_process_pid=next(iter(pids)),same_source=True,
            common_settings=settings[0],source_sha256=hashes[0],cases=records,
            scope='Three fixed Q4 business graphs; not all inputs, Q8 or Docker HTTP validation')
assert not args.output.exists(),'Preserve existing validation record'
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS same process/source, identical common parameters, original case seeds/face targets, fresh neural generation and audited exports')
