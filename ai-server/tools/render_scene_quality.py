"""Render selected frames' GT/baseline/reuse boxes; quantitative gates cover all frames.

This is a plotting utility for numeric 3D data, not a replacement for the full
regression check or the application's Rerun viewer.
"""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.lines import Line2D
    import numpy as np
    from nuscenes import NuScenes
    from nuscenes.eval.detection.utils import category_to_detection_name
    from pyquaternion import Quaternion

    manifest=json.loads((a.directory/'manifest.json').read_text())
    name='vlm_p_final_'+manifest['scene']+'_8class.json'
    baseline,reuse=[json.loads((a.directory/mode/'outs/vlm/p_final/#out_labels'/name).read_text()) for mode in ('baseline','reuse')]
    nusc=NuScenes(dataroot=manifest['data_root'],version=manifest['version'],verbose=False)
    frames=baseline.get('track_frames',list(baseline['results']))
    selected=[frames[0],frames[len(frames)//2],frames[-1]]
    colors=dict(zip(['car','truck','bus','trailer','construction_vehicle','pedestrian','motorcycle','bicycle','barrier','traffic_cone'],plt.get_cmap('tab10').colors))
    used=set();prepared=[]
    edges=[(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    def corners(box,pose):
        w,l,h=box['size'];local=np.array([[l/2,w/2,-h/2],[l/2,-w/2,-h/2],[-l/2,-w/2,-h/2],[-l/2,w/2,-h/2],
            [l/2,w/2,h/2],[l/2,-w/2,h/2],[-l/2,-w/2,h/2],[-l/2,w/2,h/2]])
        world=local@Quaternion(box['rotation']).rotation_matrix.T+np.array(box['translation'])
        return (world-np.array(pose['translation']))@Quaternion(pose['rotation']).rotation_matrix
    for token in selected:
        sample=nusc.get('sample',token);lidar=nusc.get('sample_data',sample['data']['LIDAR_TOP']);pose=nusc.get('ego_pose',lidar['ego_pose_token'])
        gt=[]
        for annid in sample['anns']:
            ann=nusc.get('sample_annotation',annid);category=category_to_detection_name(ann['category_name'])
            if category:gt.append({**ann,'detection_name':category})
        columns=[]
        for boxes in (gt,baseline['results'][token],reuse['results'][token]):
            visible=[]
            for box in boxes:
                xyz=corners(box,pose)
                if np.linalg.norm(xyz[:,:2].mean(axis=0))<=50:
                    visible.append((box['detection_name'],xyz));used.add(box['detection_name'])
            columns.append(visible)
        prepared.append(columns)
    fig,axes=plt.subplots(3,3,figsize=(14,13),layout='constrained')
    for row,columns in enumerate(prepared):
        for col,boxes in enumerate(columns):
            ax=axes[row,col]
            for category,xyz in boxes:ax.add_patch(Polygon(xyz[:4,:2],fill=False,edgecolor=colors[category],linewidth=.85,alpha=.85))
            ax.scatter([0],[0],c='black',marker='^',s=35);ax.set(xlim=(-50,50),ylim=(-50,50),aspect='equal',xlabel='ego forward (m)',ylabel='ego left (m)')
            ax.grid(alpha=.18);ax.set_title(['Ground truth','Baseline','Preprocessing reuse'][col]+f' | frame {frames.index(selected[row])} | {len(boxes)} visible boxes')
    handles=[Line2D([0],[0],color=colors[name],label=name) for name in colors if name in used]
    fig.legend(handles=handles,loc='outside lower center',ncol=5,frameon=False)
    fig.suptitle(manifest['scene']+' / same ego coordinates / boxes within 50 m\nSelected-frame visualization; full JSON comparison covers every frame',fontsize=14)
    fig.savefig(a.directory/'quality-birdseye.png',dpi=150);fig.savefig(a.directory/'quality-birdseye.svg');plt.close(fig)
    fig=plt.figure(figsize=(16,5),layout='constrained')
    for col,boxes in enumerate(prepared[1]):
        ax=fig.add_subplot(1,3,col+1,projection='3d')
        for category,xyz in boxes:
            for left,right in edges:ax.plot(*xyz[[left,right]].T,color=colors[category],linewidth=.65,alpha=.8)
        ax.set(xlim=(-50,50),ylim=(-50,50),zlim=(-4,12),xlabel='forward (m)',ylabel='left (m)',zlabel='up (m)',title=['Ground truth','Baseline','Preprocessing reuse'][col])
        ax.set_box_aspect((1,1,.25));ax.view_init(elev=27,azim=-65)
    fig.suptitle(manifest['scene']+f' / frame {frames.index(selected[1])} / identical 3D viewing transform',fontsize=14)
    fig.savefig(a.directory/'quality-3d.png',dpi=160,bbox_inches='tight',pad_inches=.2);plt.close(fig)
    (a.directory/'visualization-manifest.json').write_text(json.dumps({'scene':manifest['scene'],'sample_tokens':selected,
        'radius_m':50,'coordinates':'ego at keyframe LIDAR_TOP pose','scope':'selected visual examples; not a quantitative acceptance gate'},indent=2))
    print('Saved birdseye and 3D comparison plots.')


if __name__=='__main__':main()
