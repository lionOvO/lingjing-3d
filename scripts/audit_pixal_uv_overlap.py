"""Measure sampled UV ambiguity, excluding coincident physical surfaces."""
import argparse
import json
from pathlib import Path
import numpy as np
import shapely
import trimesh

def measure_overlap(vertices,faces,uv,sample_count=25000):
    tri_uv=uv[faces].astype(np.float64)
    a,b=tri_uv[:,1]-tri_uv[:,0],tri_uv[:,2]-tri_uv[:,0]
    det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    valid=np.flatnonzero(det!=0)
    if len(valid)==0:
        return dict(sampled_face_centroids=0,centroids_with_multiple_uv_triangles=0,
                    centroids_with_different_surface_positions=0,ambiguous_centroid_fraction=0,
                    position_separation_threshold=2/1024,max_containing_triangles=0)
    rng=np.random.default_rng(17)
    samples=rng.choice(valid,min(sample_count,len(valid)),replace=False)
    points=tri_uv[samples].mean(axis=1)
    tree=shapely.STRtree(shapely.polygons(tri_uv[valid]))
    query=tree.query(shapely.points(points),predicate='within')
    target_faces=valid[query[1]]
    offset=points[query[0]]-tri_uv[target_faces,0]
    weight1=(offset[:,0]*b[target_faces,1]-offset[:,1]*b[target_faces,0])/det[target_faces]
    weight2=(a[target_faces,0]*offset[:,1]-a[target_faces,1]*offset[:,0])/det[target_faces]
    target_positions=(vertices[faces[target_faces,0]]*(1-weight1-weight2)[:,None]+
                      vertices[faces[target_faces,1]]*weight1[:,None]+vertices[faces[target_faces,2]]*weight2[:,None])
    source_positions=vertices[faces[samples]].mean(axis=1)
    distance=np.linalg.norm(target_positions-source_positions[query[0]],axis=1)
    ambiguous=np.unique(query[0][distance>2/1024])
    coverage=np.bincount(query[0],minlength=len(samples))
    return dict(sampled_face_centroids=len(samples),
                centroids_with_multiple_uv_triangles=int((coverage>1).sum()),
                centroids_with_different_surface_positions=len(ambiguous),
                ambiguous_centroid_fraction=len(ambiguous)/len(samples),
                position_separation_threshold=2/1024,max_containing_triangles=int(coverage.max()),
                measure='Uniform sample of triangle centroids; not atlas pixel overlap fraction')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('model',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=25000)
    args=parser.parse_args()
    if args.model.suffix=='.npz':
        data=np.load(args.model)
        vertices,faces,uv=data['vertices'],data['faces'],data['uv']
    else:
        mesh=trimesh.load(args.model,force='mesh',process=False)
        vertices,faces,uv=mesh.vertices,mesh.faces,mesh.visual.uv
    row=dict(model=str(args.model),**measure_overlap(vertices,faces,uv,args.samples))
    args.output.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(row,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
