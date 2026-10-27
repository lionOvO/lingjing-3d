"""Print a pinned download plan by default. --apply downloads HF model files.

No weights are downloaded until explicitly requested. NAF and rembg use the
additional official links in engine/model-downloads.json, outside this plan.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--comfy-root',type=Path,required=True)
    parser.add_argument('--profile',choices=['q4','q8'],default='q4')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'engine/model-downloads.json').read_text(encoding='utf-8'))
    chosen=[e for e in manifest['files'] if e['profile'] in {'common',args.profile}]
    destination=args.comfy_root.resolve()
    print(f'{args.profile}: {len(chosen)} files, {sum(e.get("bytes") or 0 for e in chosen)/1e9:.2f} GB')
    for e in chosen:print(e['local_path'])
    if not args.apply:
        print('Plan only. Add --apply to download; read model licenses first.');return
    from huggingface_hub import hf_hub_download
    import shutil
    for e in chosen:
        target=(destination/e['local_path']).resolve()
        if not target.is_relative_to(destination):raise RuntimeError('Destination escapes engine directory')
        source=Path(hf_hub_download(repo_id=e['repo_id'],filename=e['filename'],revision=e['revision']))
        if e.get('sha256'):
            digest=hashlib.sha256()
            with source.open('rb') as stream:
                for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
            if digest.hexdigest()!=e['sha256']:raise RuntimeError('Checksum mismatch: '+e['filename'])
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.resolve()!=target:shutil.copy2(source,target)
    print('HF files downloaded and available LFS SHA256 values verified. See additional links for NAF/rembg.')

if __name__=='__main__':main()
