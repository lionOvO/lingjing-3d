"""Measure fixed-mesh projection coverage against the reference foreground."""
from pathlib import Path
import json
import numpy as np
import trimesh
from PIL import Image

ROOT = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
mesh = trimesh.load(ROOT/'output/Pixal3D_Geometry_512_00001_.glb', force='mesh', process=False)
v = np.asarray(mesh.vertices)
v = (v - (v.min(0)+v.max(0))/2) * (0.99999/np.ptp(v,axis=0).max())
points = np.stack([v[:,0], -v[:,2], v[:,1]], -1)[::20]
image = Image.open(ROOT/'input/OIP_clean_1024_rgba.png')
left, top, right, bottom = image.getchannel('A').getbbox()
target = np.array([(right-left)/image.width, (bottom-top)/image.height])
focal = 0.5 / np.tan(0.8575560450553894/2)
def extent(distance):
    projection = focal * points[:,[0,2]] / (distance + points[:,1:2])
    return np.ptp(projection, axis=0)
lo = max(0.01, -points[:,1].min()+0.01)
hi = 10.0
for _ in range(40):
    middle = (lo+hi)/2
    if np.max(extent(middle)/target)>1:
        lo = middle
    else:
        hi = middle
print(json.dumps({'foreground_extent':target.tolist(),'old_camera_extent':extent(2.0).tolist(),'fitted_distance':hi,'fitted_extent':extent(hi).tolist()},indent=2))
