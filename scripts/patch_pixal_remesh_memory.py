"""Install the verified native memory patch and align existing SciPy imports."""
import ast
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\cumesh\remeshing.py')
backup=path.with_name(path.name+'.bak-before-memory-lifetime-20261009')
assert not backup.exists()
assert hashlib.sha256(path.read_bytes()).hexdigest()=='17ae808aa7d0ed7d95bd7016a6c86b30d9b1b2bc5451a82e8bee348ccf88516d'
source=(ROOT/'tmp/pixal-cumesh-remesh-memory-candidate-20261009.py').read_text(encoding='utf-8')
ast.parse(source);backup.write_bytes(path.read_bytes());path.write_text(source,encoding='utf-8',newline='\n')
print('CuMesh SHA',hashlib.sha256(path.read_bytes()).hexdigest())
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
backup=path.with_name(path.name+'.bak-before-module-scipy-imports-20261009')
assert not backup.exists()
assert hashlib.sha256(path.read_bytes()).hexdigest()=='f8ccd72b6404e3c9b3cc88de7a262c6c325d579c8fa5c21ff6b3d59c480450f9'
source=path.read_text(encoding='utf-8')
source=source.replace('import pymeshlab\n','import pymeshlab\nfrom scipy.sparse import coo_matrix\nfrom scipy.sparse.csgraph import connected_components\n',1)
source=source.replace('        from scipy.sparse import coo_matrix\n        from scipy.sparse.csgraph import connected_components\n','',1)
ast.parse(source);backup.write_bytes(path.read_bytes());path.write_text(source,encoding='utf-8',newline='\n')
print('Nodes SHA',hashlib.sha256(path.read_bytes()).hexdigest())
