import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import app
from services.vespa_service import VespaService, VespaError
from schemas.auto_label import AutoLabelRequest
import clip_core

@pytest.fixture
def service(tmp_path,monkeypatch):
    monkeypatch.setenv('VESPA_RIGID_ENABLED','false')  # Legacy subprocess fixture has no tracklet implementation.
    repo=tmp_path/'repo'; (repo/'configs/vlm').mkdir(parents=True)
    (repo/'configs/vlm/p_final.yaml').write_text('type: vlm\ndata:\n  dataset: nuscenes\ngrounding_sam:\n  class_names: [car]\n')
    (repo/'main_pseudo_union.py').write_text("from pathlib import Path\nEXP_PSEUDO_OUT_PATH=Path('outs')\ndef get_out_dir(config,module):\n p=EXP_PSEUDO_OUT_PATH/config['type']/config['exp_name']/module\n p.mkdir(parents=True,exist_ok=True)\n return p\n")
    (repo/'main_pseudo_vlm.py').write_text("""import os,time
from main_pseudo_union import get_out_dir

def process_scene(scene,infos,config,args):
 mode=os.environ.get('TEST_VESPA_MODE','ok')
 if mode=='timeout': time.sleep(5)
 if mode=='exit': raise RuntimeError('synthetic failure')
 get_out_dir(config,'01_remove_ground').joinpath('test.npz').write_text('not returned')
 results={}
 for mapping,cls in [('1class','vehicle'),('3class','pedestrian'),('8class','car')]:
  box={'sample_token':'sample-a','translation':[1,2,3],'size':[2,4,1],'rotation':[1,0,0,0],
       'velocity':[0,0],'detection_name':cls,'detection_score':1.0,'attribute_name':''}
  if mode=='bad-box': box['sample_token']='other'
  token='unexpected' if mode=='bad-coverage' else 'sample-a'
  results[mapping]={token:[box],'sample-empty':[]}
 return results,'mini_train'
""")
    for package in ('src','src/labeling'):
        p=repo/package; p.mkdir(exist_ok=True); (p/'__init__.py').write_text('')
    (repo/'src/labeling/prior_info.py').write_text('def get_common_object_infos_sam(classes): return {}\n')
    (repo/'src/labeling/submission.py').write_text('def _get_annotation_dict(box,token): return box\n')
    data=tmp_path/'data/v1.0-mini'; data.mkdir(parents=True)
    (data/'scene.json').write_text(json.dumps([{'name':'scene-0061','token':'scene-token'}]))
    (data/'sample.json').write_text(json.dumps([{'token':t,'scene_token':'scene-token'} for t in ['sample-a','sample-empty']]))
    for key,value in {'VESPA_ROOT':repo,'VESPA_PYTHON':sys.executable,'VESPA_DATA_ROOT':data.parent,
        'VESPA_DATASET_VERSION':'v1.0-mini','VESPA_OUTPUT_ROOT':tmp_path/'runs','VESPA_TIMEOUT_SECONDS':'10'}.items():
        monkeypatch.setenv(key,str(value))
    return VespaService()

@pytest.mark.parametrize('mode',[1,3,8])
def test_subprocess_json(service,mode):
    assert service.python==Path(sys.executable).absolute()
    result=service.generate(AutoLabelRequest(scene_name='scene-0061',class_mode=mode))
    assert result.mapping_name==f'{mode}class'
    assert result.results['sample-empty']==[]
    assert result.coordinate_frame=='WORLD'
    assert len(result.result_checksum)==64
    assert (service.output_root/result.artifact_path).is_file()
    assert '#out_labels' in result.artifact_path
    second=service.generate(AutoLabelRequest(scene_name='scene-0061',class_mode=mode))
    assert second.run_id!=result.run_id

@pytest.mark.parametrize('mode,code',[('exit','VESPA_EXECUTION_FAILED'),('bad-box','VESPA_INVALID_RESULT'),('bad-coverage','VESPA_INVALID_RESULT'),('timeout','VESPA_TIMEOUT')])
def test_errors(service,monkeypatch,mode,code):
    monkeypatch.setenv('TEST_VESPA_MODE',mode)
    if mode=='timeout': service.timeout=1
    with pytest.raises(VespaError) as caught:
        service.generate(AutoLabelRequest(scene_name='scene-0061'))
    assert caught.value.code==code
    assert service.lock.acquire(blocking=False)
    service.lock.release()


def test_busy_unknown_and_unconfigured(service):
    service.lock.acquire()
    with pytest.raises(VespaError) as caught: service.generate(AutoLabelRequest(scene_name='scene-0061'))
    assert caught.value.status_code==409
    service.lock.release()
    with pytest.raises(VespaError) as caught: service.generate(AutoLabelRequest(scene_name='scene-9999'))
    assert caught.value.status_code==404
    service.python=Path('/no-python')
    with pytest.raises(VespaError) as caught: service.generate(AutoLabelRequest(scene_name='scene-0061'))
    assert caught.value.status_code==503

def test_postprocess_source_is_confined_and_requires_cache(service, tmp_path):
    from uuid import uuid4
    run = service.output_root / str(uuid4())
    run.mkdir(parents=True)
    (run / 'result.json').write_text('{}')
    relative = str((run / 'result.json').relative_to(service.output_root))
    with pytest.raises(VespaError): service._source_run(relative)
    (run / 'rigid-manifest.json').write_text('{}')
    (run / 'rigid-state.pkl.gz').write_bytes(b'fixture')
    assert service._source_run(relative) == run
    for path in ('../result.json', str(run / 'result.json'), 'invalid/result.json', 'a\\b'):
        with pytest.raises(VespaError): service._source_run(path)


def test_api(service):
    with patch.object(clip_core,'load_model',return_value=(object(),None,None)):
        with TestClient(app) as client:
            app.state.vespa_service=service
            r=client.post('/auto-label',json={'scene_name':'scene-0061','class_mode':8,'job_id':7,'execution_token':'00000000-0000-0000-0000-000000000001'})
            assert r.status_code==200,r.text
            assert r.json()['job_id']==7
            assert r.json()['results']['sample-empty']==[]
            for body in [{'scene_name':'../bad'},{'scene_name':'scene-0061','class_mode':2},{'scene_name':'scene-0061','job_id':1}]:
                assert client.post('/auto-label',json=body).status_code==422


def test_missing_output(service,monkeypatch):
    service.num_threads=2
    import services.vespa_service as module
    class CompletedWithoutOutput:
        def __init__(self,*args,**kwargs):
            for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
                assert kwargs["env"][key]=="2"
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def wait(self,timeout=None): return 0
    monkeypatch.setattr(module.subprocess,"Popen",CompletedWithoutOutput)
    with pytest.raises(VespaError) as caught:
        service.generate(AutoLabelRequest(scene_name="scene-0061"))
    assert caught.value.code=="VESPA_INVALID_RESULT"
