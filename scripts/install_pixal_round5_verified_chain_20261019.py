"""Promote only the combined NAF/factory/cleanup-order change after real stage checks."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[1]
def read(name): return json.loads((ROOT / 'tmp' / name).read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 8188)) != 0
assert read('pixal-round5-visual-assessment-20261019.json')['combined_candidate_accepted']
reports = [read(f'pixal-postprocess-round5-clean-after-remesh-{case}-20261019.json') for case in ('person', 'robot', 'helmet')]
for report in reports:
    assert report['trial_floaters_after_remesh'] and report['remove_floaters'] and report['trial_floater_ratio'] is None
    assert Path(report['model']).is_file()
for case in ('person', 'robot', 'helmet'):
    geometry = read(f'pixal-round5-final-{case}-geometry-20261019.json')
    assert geometry['finite_vertices'] and geometry['zero_area_faces'] == 0 and geometry['same_winding_duplicate_faces'] == 0
    # Existing third-round baselines were 0 / 34 / 2; do not call the helmet's
    # two retained UV degeneracies fixed or promote an increased count.
    assert geometry['zero_uv_area_faces'] <= {'person': 0, 'robot': 34, 'helmet': 2}[case]
naf = read('pixal-naf-global-installed-20261019.json')
factory = read('pixal-local-condition-factory-installed-20261019.json')
assert read('pixal-local-condition-factory-regression-20261019.json')['completed']
for report in (naf, factory):
    assert sha(report['path']) == report['before_sha256']
    assert sha(ROOT / 'tmp/pixal-round5-candidate-sources-20261019' / Path(report['path']).name) == report['sha256']
nodes = Path(naf['path']).parents[4] / 'nodes.py'
assert nodes.is_file() and sha(nodes) == 'aa72fdc9e81ad325fd5edf7901ef33ee2a108172d24b3219fc2993d89c16b3e0'
source = nodes.read_text(encoding='utf-8')
tree = ast.parse(source)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process')
old = ast.get_source_segment(source, method)
new = old.replace('''        if remove_floaters:
            mesh_copy = MeshUtils.remove_floater(mesh_copy)''', '''        # Raw dual-grid fragments can form valid strands after reconstruction.
        # The remesh branch cleans components after rebuilding their connections.
        if remove_floaters and not remesh:
            mesh_copy = MeshUtils.remove_floater(mesh_copy)''', 1)
assert new != old
changed = source.replace(old, new, 1)
tree = ast.parse(changed)
helpers = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('MeshUtils', 'ImageUtils')]
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process')
executed_ast = hashlib.sha256(ast.dump(ast.Module(body=helpers+[method], type_ignores=[]), include_attributes=False).encode()).hexdigest()
assert all(r['executed_ast_sha256'] == executed_ast for r in reports)
backup = nodes.with_name(nodes.name + '.bak-before-deferred-floaters-20261019')
assert not backup.exists()
backup.write_bytes(nodes.read_bytes())
nodes.write_text(changed, encoding='utf-8', newline='\n')
for report in (naf, factory):
    Path(report['path']).write_bytes((ROOT / 'tmp/pixal-round5-candidate-sources-20261019' / Path(report['path']).name).read_bytes())
    assert sha(report['path']) == report['sha256']
patch = ''.join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True), fromfile='before/nodes.py', tofile='after/nodes.py'))
(ROOT / 'docs/Pixal3D_第五轮清理顺序修复_20261019.patch').write_text(patch, encoding='utf-8')
record = dict(candidate_deployed=True, validation_mode='One fresh neural generation plus three real saved-neural postprocess executions; final postprocess AST exactly matches installed source.',
              naf=naf, factory=factory, nodes=dict(path=str(nodes), before_sha256=sha(backup), sha256=sha(nodes), backup=str(backup)),
              executed_postprocess_ast_sha256=executed_ast)
target = ROOT / 'tmp/pixal-round5-final-installed-20261019.json'
assert not target.exists()
target.write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, indent=2))
