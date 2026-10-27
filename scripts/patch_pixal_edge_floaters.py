"""Install the verified edge filter only at the failing post-remesh call site."""
import ast
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
backup=path.with_name(path.name+'.bak-before-edge-floaters-20261009')
assert not backup.exists(),'Already installed: inspect rather than reapply'
assert hashlib.sha256(path.read_bytes()).hexdigest()=='200e5a3e6ec908fc9ff42adb3072cfecf9fc2e90410334279804c8c8d06b0ee4'
source=path.read_text(encoding='utf-8')
helper=(ROOT/'tmp/pixal-edge-floater-candidate.py').read_text()
helper='    @staticmethod\n'+''.join('    '+line+'\n' for line in helper.splitlines())+'\n'
source=source.replace('class MeshUtils:\n','class MeshUtils:\n'+helper,1)
anchor='new_vertices, new_faces = MeshUtils.remove_floater2(new_vertices.cpu().numpy(),new_faces.cpu().numpy())'
assert source.count(anchor)==1
source=source.replace(anchor,'''new_vertices, new_faces = MeshUtils.remove_floater_by_edges(new_vertices.cpu().numpy(), new_faces.cpu().numpy())
                # Reinitialization must not reuse topology from the pre-filter mesh.
                cumesh.clear_cache()''',1)
ast.parse(source)
backup.write_bytes(path.read_bytes())
path.write_text(source,encoding='utf-8',newline='\n')
print('Installed post-remesh edge filtering',hashlib.sha256(path.read_bytes()).hexdigest())
