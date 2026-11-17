import importlib.util
import json
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


scene=module('scene_comparison',ROOT/'ai-server/tools/compare_scene.py')
index=module('index_comparison',ROOT/'scripts/hybrid/compare_index_cases.py')
roundtrip=module('label_roundtrip',ROOT/'scripts/hybrid/compare_label_roundtrip.py')


class ComparisonTest(unittest.TestCase):
    def test_float_roundoff_is_separate_from_exact_equality(self):
        result=scene.compare({'translation':[1.,2.,3.]},{'translation':[1.0000001,2.,3.]})
        self.assertTrue(result['within_tolerance']);self.assertFalse(result['exact'])

    def test_identity_loss_and_nonfinite_values_fail(self):
        for a,b in [({'track_id':1},{'track_id':2}),({'boxes':[]},{'boxes':[{}]}),
                    ({'token':'a'},{'token':'b'}),({'x':float('nan')},{'x':float('nan')})]:
            self.assertFalse(scene.compare(a,b)['within_tolerance'])

    def vector_file(self,token='a',value=None):
        value=value if value is not None else [1.]+[0.]*767
        return {'model':'model','preprocess':'same','vectors':[{'sample_data_token':token,'embedding':json.dumps(value)}]}

    def test_vector_ids_and_geometry_are_verified(self):
        original=self.vector_file()
        self.assertTrue(index.vectors_match(original,self.vector_file())['passed'])
        self.assertFalse(index.vectors_match(original,self.vector_file(token='b'))['passed'])
        self.assertFalse(index.vectors_match(original,self.vector_file(value=[0.]*768))['passed'])
        other=self.vector_file();other['model']='other'
        self.assertFalse(index.vectors_match(original,other)['passed'])

    def test_duplicate_vector_rows_cannot_mask_missing_images(self):
        value=self.vector_file();value['vectors']*=2
        self.assertFalse(index.vectors_match(value,self.vector_file())['passed'])

    def test_ranking_order_and_best_image_regression(self):
        left=[{'parameters':{'q':'road'},'response':{'scenes':[{'sceneToken':'a','score':.5,'bestSampleToken':'first'},{'sceneToken':'b','score':.4}]}}]
        self.assertTrue(index.rankings_match(left,left)['passed'])
        changed=json.loads(json.dumps(left));changed[0]['response']['scenes'].reverse()
        self.assertFalse(index.rankings_match(left,changed)['passed'])
        changed=json.loads(json.dumps(left));changed[0]['response']['scenes'][0]['bestSampleToken']='other'
        self.assertFalse(index.rankings_match(left,changed)['passed'])
        empty=[{'parameters':{'q':'road'},'response':{'scenes':[]}}]
        self.assertFalse(index.rankings_match(empty,empty)['passed'])
        changed=json.loads(json.dumps(left));changed[0]['response']['scenes'][0]['score']=float('nan')
        self.assertFalse(index.rankings_match(left,changed)['passed'])

    def test_db_counters_distinguish_unavailable_from_observed_zero(self):
        self.assertFalse(index.database_delta({}, {})['available'])
        before={'pg_stat_statements':[{'queryid':1,'calls':5,'total_exec_time_ms':10,'kind':'vector_exists'}]}
        after={'pg_stat_statements':[{'queryid':1,'calls':7,'total_exec_time_ms':13,'kind':'vector_exists'}]}
        self.assertEqual(index.database_delta(before,after)['by_kind']['vector_exists']['calls'],2)
        self.assertTrue(index.database_delta(after,before)['reset_detected'])

    def test_restart_conditions_reject_retained_backend_or_restarted_ai(self):
        original=[{'image_digests':['backend-image','ai-image'],'backend_instance':str(i),'ai_instance':'one-ai'} for i in range(6)]
        self.assertTrue(index.runtime_conditions(original)['passed'])
        for field,value in [('backend_instance','0'),('ai_instance','restarted-ai'),('image_digests',['other-image','ai-image'])]:
            changed=json.loads(json.dumps(original));changed[1][field]=value
            self.assertFalse(index.runtime_conditions(changed)['passed'])
        missing=json.loads(json.dumps(original));missing[0]['backend_instance']=None
        self.assertFalse(index.runtime_conditions(missing)['passed'])

    def test_rds_roundtrip_detects_changed_geometry_or_track(self):
        box={'sample_token':'a','translation':[1.,2.,3.],'size':[4.,5.,6.],
             'rotation':[1.,0.,0.,0.],'velocity':[.1,.2],'detection_name':'car',
             'detection_score':1.,'attribute_name':'','track_id':3}
        original={'mapping_name':'8class','results':{'a':[box],'b':[]}}
        checksum=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        api={'mappingName':'8class','coordinateFrame':'WORLD','scoreType':'VESPA_CONSTANT','sampleTokens':['a','b'],
             'artifacts':[{'artifactType':'FINAL_JSON','checksum':checksum}],
             'boxes':[{'sampleToken':'a','boxIndex':0,'centerX':1.,'centerY':2.,'centerZ':3.,
                       'sizeW':4.,'sizeL':5.,'sizeH':6.,'rotationW':1.,'rotationX':0.,'rotationY':0.,'rotationZ':0.,
                       'velocityX':.1,'velocityY':.2,'detectionName':'car','detectionScore':1.,'attributeName':'',
                       'trackId':3,'labelOverride':None,'deleted':False}]}
        self.assertTrue(roundtrip.verify(original,api)['passed'])
        for field,value in [('centerZ',3.1),('sizeL',4.),('trackId',4),('boxIndex',1)]:
            changed=json.loads(json.dumps(api));changed['boxes'][0][field]=value
            self.assertFalse(roundtrip.verify(original,changed)['passed'])


if __name__=='__main__':unittest.main(verbosity=2)
