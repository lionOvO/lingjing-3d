"""Fail closed on forbidden tracked files, large files and recognizable secrets.

Print filenames/line numbers only, never the matched secret. This complements
review and .gitignore; it cannot recognize every possible private value.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_DIRS = {'.venv','node_modules','__pycache__','dist','.uv-cache','.uv-python',
                '.codex','.workbuddy','.pytest_cache','.runtime-wheels','tmp','exports',
                'deliverables','submission_staging','3d-toolchain'}
BLOCKED_EXT = {'.gguf','.safetensors','.ckpt','.pt','.pth','.onnx','.bin','.whl',
               '.db','.sqlite','.sqlite3','.log','.pem','.key','.p12','.pfx','.pyc'}
PATTERNS = [
    ('github-token', r'\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    ('provider-token', r'(?<![A-Za-z0-9_/-])sk-[A-Za-z0-9_-]{24,}\b'),
    ('huggingface-token', r'\bhf_[A-Za-z0-9]{30,}\b'),
    ('cloud-access-key', r'\b(?:AKIA[A-Z0-9]{16}|LTAI[A-Za-z0-9]{16,})\b'),
    ('private-key', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('credential-in-url', r'https?://[^\s/:@]+:[^\s/@]+@'),
]
REGEX = [(kind,re.compile(pattern)) for kind,pattern in PATTERNS]
SAFE_EXAMPLE = re.compile(r'(example|placeholder|replace|your[-_]|change[-_]|dummy|fake|test[-_])',re.I)
LITERAL = re.compile(r'''(?i)(?:api_key|api_secret|access_key_secret|auth_token)\s*["']?\s*[:=]\s*["']([A-Za-z0-9_./+=-]{24,})["']''')

def git_files(staged):
    cmd = ['git','diff','--cached','--name-only','--diff-filter=ACMR','-z'] if staged else ['git','ls-files','-z']
    result = subprocess.run(cmd,cwd=ROOT,capture_output=True,check=True)
    return [Path(x.decode('utf-8')) for x in result.stdout.split(b'\0') if x]

def inspect(paths, staged=False):
    issues=[]
    for rel in paths:
        name=rel.as_posix();parts=set(rel.parts)
        if parts & BLOCKED_DIRS or rel.suffix.lower() in BLOCKED_EXT or \
           (rel.name.startswith('.env') and not rel.name.endswith('.example')) or \
           rel.name=='local-stack.json' or '.bak' in rel.name or \
           (rel.suffix.lower() in {'.glb','.gltf','.fbx','.obj','.stl'} and not name.startswith('frontend/public/showcase/')):
            issues.append((name,0,'forbidden-file'));continue
        if staged:
            data=subprocess.run(['git','show',':'+name],cwd=ROOT,capture_output=True,check=True).stdout
        else:
            data=(ROOT/rel).read_bytes()
        if len(data)>25*1024*1024:issues.append((name,0,'file-over-25-MiB'))
        if b'\x00' in data[:8192]:continue
        try:text=data.decode('utf-8-sig')
        except UnicodeError:continue
        for i,line in enumerate(text.splitlines(),1):
            for kind,pattern in REGEX:
                if pattern.search(line):
                    # Deliberate redaction fixture; reserved .invalid host, never a real endpoint.
                    if kind=='credential-in-url' and name=='backend/tests/test_failure_diagnosis.py' and 'private.invalid/path?token=secret' in line:
                        continue
                    issues.append((name,i,kind))
            for match in LITERAL.finditer(line):
                value=match.group(1)
                if not SAFE_EXAMPLE.search(value) and len(set(value))>10:
                    issues.append((name,i,'credential-literal-review'))
    return issues

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--staged',action='store_true');parser.add_argument('--all-files',action='store_true');args=parser.parse_args()
    if args.all_files:
        paths=[]
        import os
        for directory,dirs,files in os.walk(ROOT):
            dirs[:]=[d for d in dirs if d!='.git']
            paths.extend((Path(directory)/f).relative_to(ROOT) for f in files)
    else:paths=git_files(args.staged)
    issues=inspect(paths,args.staged)
    for name,line,kind in issues:print(f'{name}:{line}: {kind}')
    if issues:
        print(f'BLOCKED: {len(issues)} finding(s); values were not printed.');return 1
    print(f'PASS: {len(paths)} file(s); no forbidden file/size/recognized-secret findings.');return 0

if __name__=='__main__':sys.exit(main())
