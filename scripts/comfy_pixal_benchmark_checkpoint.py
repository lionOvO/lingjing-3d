"""Temporary local benchmark output node; keep neural predictions before native postprocessing."""
import json
from pathlib import Path
import numpy as np

class PixalBenchmarkSaveMesh:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'mesh': ('MESHWITHVOXEL',)}}
    RETURN_TYPES = ('MESHWITHVOXEL',)
    FUNCTION = 'save'
    CATEGORY = 'Pixal3D benchmark'
    OUTPUT_NODE = True

    def save(self, mesh):
        path = Path(r'D:\灵境造物\tmp\pixal-final-neural-mesh-20261009.npz')
        layout = {k: [v.start, v.stop, v.step] if isinstance(v, slice) else v for k, v in mesh.layout.items()}
        arrays = {name: getattr(mesh, name).detach().cpu().numpy() for name in ('vertices','faces','coords','attrs')}
        np.savez_compressed(path, **arrays, voxel_size=np.asarray(mesh.voxel_size),
            voxel_shape=np.asarray(mesh.voxel_shape), layout=np.asarray(json.dumps(layout)),
            coordinate_system=np.asarray(mesh.coordinate_system))
        print(f'[Pixal benchmark] Neural mesh checkpoint saved: {path}', flush=True)
        return (mesh,)

NODE_CLASS_MAPPINGS = {'PixalBenchmarkSaveMesh': PixalBenchmarkSaveMesh}
