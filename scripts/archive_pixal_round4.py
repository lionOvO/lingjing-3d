"""Archive the installed packing fix and its bounded diagnostic evidence."""
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh

root=Path(__file__).resolve().parents[1];tmp=root/'tmp'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
sources=read(tmp/'pixal-round4-source-sha-20261012.json')
assert all(sha(r['path'])==r['sha256'] for r in sources)
installed=read(tmp/'pixal-round4-installed-validation-20261012.json')
assert len(installed)==3 and all(r['installed_default_exact_to_baked_candidate'] for r in installed)
fixtures=read(tmp/'pixal-round4-padding-clearance-fixtures-20261012.json')
assert len(fixtures)==480 and all(not r['spacing_violation'] for r in fixtures if r['version']=='candidate')
spacing=read(tmp/'pixal-round4-pixel-spacing-20261012.json')
assert len(spacing)==18
assert all(r['nearby_pairs_below_two_pixels']==0 and r['aabb_overlap_pairs']==0 for r in spacing if r['variant'].startswith('padded'))
colors=read(tmp/'pixal-round4-surface-colors-20261012.json');assert len(colors)==21
bakes=read(tmp/'pixal-fixed-geometry-uv-comparison-20261012-padding.json');assert len(bakes)==9
controls=[];renders=[]
for row in bakes:
    key=f"{row['case']}-{row['variant']}-20261012"
    quality=read(tmp/f'pixal-round4-export-quality-{key}.json')
    overlap=read(tmp/f'pixal-round4-overlap-{key}.json')
    assert row['ordered_geometry_exact'] and row['missing_voxel_samples']==row['valid_pixels_changed_by_inpaint']==0
    assert quality['zero_area_faces']==quality['same_winding_duplicate_faces']==0 and quality['finite_vertices']
    mesh=trimesh.load(row['model'],force='mesh',process=False)
    triangle=mesh.vertices[mesh.faces].astype(np.float64);uv=mesh.visual.uv[mesh.faces].astype(np.float64)
    area=np.linalg.norm(np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0]),axis=1)*.5
    a,b=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0];zero=a[:,0]*b[:,1]-a[:,1]*b[:,0]==0
    thin=dict(zero_uv_faces=int(zero.sum()),largest_zero_uv_geometric_area=float(area[zero].max()) if zero.any() else 0,
              zero_uv_surface_area_fraction=float(area[zero].sum()/area.sum()))
    controls.append(dict(bake=row,export_quality=quality,overlap=overlap,zero_uv_geometry=thin,sha256=sha(row['model'])))
    for mode in ('original','base'):
        for axis in ('plusz','plusy','angle'):
            path=tmp/f"{Path(row['model']).stem}_{mode}_{axis}.png"
            renders.append(dict(path=str(path),sha256=sha(path)))
refs=read(tmp/'pixal-round4-neural-color-reference-linear-20261012.json');assert len(refs)==3
for row in refs:
    assert row['missing_samples']==0 and row['ordered_geometry_exact']
    row['sha256']=sha(row['model'])
    for axis in ('plusz','plusy','angle'):
        path=tmp/f"{Path(row['model']).stem}_base_{axis}.png"
        renders.append(dict(path=str(path),sha256=sha(path)))
assert len(renders)==63
gray=read(tmp/'pixal-round4-color-space-render-check-20261012.json');assert gray['pass']
smoke=read(tmp/'pixal-round4-viewer-smoke-20261012.json')
assert len(smoke)==1 and smoke[0]['reviewed_current_models']==15 and not smoke[0]['page_errors']
out=tmp/'pixal-round4-final-validation-20261012.json'
assert not out.exists(), 'Preserve final evidence'
out.write_text(json.dumps(dict(installed_sources=sources,installed_uv_exact=installed,
    fixture_layouts=240,spacing=spacing,colors=colors,controls=controls,
    neural_vertex_references=refs,color_space_render_check=gray,renders=renders,viewer_smoke=smoke,
    installed_change='Only account for two-sided margin when fitting an island into a packing hole and updating its leftovers.',
    defaults='Margin .01, atlas1024, NAF K4, UV orientation/merge settings, geometry, weights and neural sampling unchanged.',
    rejected='Half-margin improves base-level density but some controlled level2 color errors increase; orientation-half still loses fidelity. Not installed.',
    scope='Three fixed final geometries include existing UV seams. Nine native neural-texture re-bakes, not nine fresh neural generations. Installed default UV arrays exact to three audited candidate bakes. Controlled mip levels are not camera derivatives.',
    unresolved='Neural-color reference still shows skin/eye mismatch and geometric gaps. Default person6/robot2 tiny zero-UV faces remain; no visible global color correction claimed.'),
    ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS round4 archive: installed fix, 18 unwrap measurements, 21 color controls, 9 bakes, 63 renders and 15 viewer samples')
