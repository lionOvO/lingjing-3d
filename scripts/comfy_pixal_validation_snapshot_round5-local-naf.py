"""Temporary local output node for reproducible neural predictions."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(r'D:\灵境造物\tmp')
PATHS={case:ROOT/f'pixal-round5-local-naf-{case}-prediction-20261019.npz' for case in ('person','robot','helmet')}

class PixalValidationSnapshot:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'mesh':('MESHWITHVOXEL',),'case':(list(PATHS),)}}
    RETURN_TYPES=('MESHWITHVOXEL',)
    FUNCTION='save'
    CATEGORY='Pixal3D validation'
    OUTPUT_NODE=True

    def save(self,mesh,case):
        path=PATHS[case]
        if path.exists():
            raise FileExistsError(f'Preserve previous prediction: {path}')
        arrays={name:getattr(mesh,name).detach().cpu().contiguous().numpy() for name in ('vertices','faces','coords','attrs')}
        layout={key:[value.start,value.stop,value.step] if isinstance(value,slice) else value for key,value in mesh.layout.items()}
        np.savez(path,**arrays,voxel_size=np.asarray(mesh.voxel_size),voxel_shape=np.asarray(mesh.voxel_shape),
                 layout=np.asarray(json.dumps(layout)),coordinate_system=np.asarray(mesh.coordinate_system))
        meta={name:dict(shape=list(array.shape),dtype=str(array.dtype),sha256=hashlib.sha256(memoryview(array).cast('B')).hexdigest()) for name,array in arrays.items()}
        path.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        print(f'[Pixal validation] Saved neural prediction {case}',flush=True)
        return (mesh,)

NODE_CLASS_MAPPINGS={'PixalValidationSnapshot':PixalValidationSnapshot}
