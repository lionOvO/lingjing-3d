"""Install narrow cleanup around hole filling, preserving face winding and positions."""
import ast
from pathlib import Path

path = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
backup = path.with_name(path.name + '.bak-before-mesh-cleanup-20261009')
if backup.exists():
    raise RuntimeError('Cleanup backup already exists; inspect installed source instead of reapplying')
source = path.read_text(encoding='utf-8')
anchor = 'class MeshUtils:\n'
helper = '''class MeshUtils:
    @staticmethod
    def clean_mesh_faces(vertices, faces):
        # Test exact area in float64 without discarding small but valid triangles.
        triangles = vertices[faces].astype(np.float64)
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        valid = np.any(cross != 0, axis=1)
        faces = faces[valid]
        # Compare positions without welding split vertices or removing reverse faces.
        _, position_ids = np.unique(vertices, axis=0, return_inverse=True)
        keys = position_ids[faces]
        rotation = keys.argmin(axis=1)
        keys = np.take_along_axis(keys, (rotation[:, None] + np.arange(3)) % 3, axis=1)
        _, first = np.unique(keys, axis=0, return_index=True)
        return np.ascontiguousarray(faces[np.sort(first)])

'''
assert source.count(anchor) == 1
source = source.replace(anchor, helper, 1)
before = '''        if fill_holes:
            new_vertices, new_faces = cumesh.read()
            meshlib_mesh = mrmeshnumpy.meshFromFacesVerts(new_faces.detach().clone().cpu().numpy(), new_vertices.detach().clone().cpu().numpy())'''
after = '''        new_vertices, new_faces = cumesh.read()
        new_vertices = new_vertices.detach().cpu().numpy()
        new_faces = MeshUtils.clean_mesh_faces(new_vertices, new_faces.detach().cpu().numpy())

        if fill_holes:
            meshlib_mesh = mrmeshnumpy.meshFromFacesVerts(new_faces, new_vertices)'''
assert source.count(before) == 1
source = source.replace(before, after, 1)
before = '''            new_vertices = mrmeshnumpy.getNumpyVerts(meshlib_mesh)
            new_faces = mrmeshnumpy.getNumpyFaces(meshlib_mesh.topology)

            del meshlib_mesh
            gc.collect()
            
            # init replaces geometry but retains CuMesh topology caches.
            cumesh.clear_cache()
            cumesh.init(torch.from_numpy(new_vertices).float().to(coords.device), torch.from_numpy(new_faces).int().to(coords.device))'''
after = '''            new_vertices = mrmeshnumpy.getNumpyVerts(meshlib_mesh).astype(np.float32, copy=False)
            new_faces = MeshUtils.clean_mesh_faces(new_vertices, mrmeshnumpy.getNumpyFaces(meshlib_mesh.topology))

            del meshlib_mesh
            gc.collect()

        # init replaces geometry but retains CuMesh topology caches.
        cumesh.clear_cache()
        cumesh.init(torch.from_numpy(new_vertices).float().to(coords.device), torch.from_numpy(new_faces).int().to(coords.device))
        cumesh.remove_unreferenced_vertices()
        cumesh.clear_cache()'''
assert source.count(before) == 1
source = source.replace(before, after, 1)
ast.parse(source)
backup.write_bytes(path.read_bytes())
path.write_text(source, encoding='utf-8', newline='\n')
print('Installed cleanup; backup:', backup)
