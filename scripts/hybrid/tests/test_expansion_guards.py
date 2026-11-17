import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_grounding_variants import geometry_diagnostic
from run_query_experiment import summarize_plan


class ExpansionGuardsTest(unittest.TestCase):
    def test_same_count_but_different_class_is_not_a_match(self):
        left={'camera':[{'label':'car','score':.8,'box':{'xmin':0,'ymin':0,'xmax':10,'ymax':10}}]}
        right=copy.deepcopy(left);right['camera'][0]['label']='truck'
        result=geometry_diagnostic(left,right)
        self.assertFalse(result['same_per_image_class_counts'])
        self.assertEqual((result['matched'],result['unmatched_reference'],result['unmatched_candidate']),(0,1,1))

    def test_duplicate_boxes_cannot_match_one_reference_twice(self):
        box={'label':'car','score':.8,'box':{'xmin':0,'ymin':0,'xmax':10,'ymax':10}}
        result=geometry_diagnostic({'camera':[box,box]},{'camera':[box]})
        self.assertEqual(result['matched'],1);self.assertEqual(result['unmatched_reference'],1)
        self.assertFalse(geometry_diagnostic({'left':[box]},{'right':[box]})['same_image_set'])

    def test_exported_plan_omits_vector_literals_recursively(self):
        node={'Node Type':'Sort','Filter':'private vector literal','Output':['embedding secret'],
              'Plans':[{'Node Type':'Index Scan','Index Name':'example','Actual Rows':3,'Index Cond':'secret',
                        'Shared Hit Blocks':8,'Temp Written Blocks':4}]}
        result=summarize_plan(node)
        self.assertNotIn('Filter',result);self.assertNotIn('Output',result)
        self.assertNotIn('Index Cond',result['Plans'][0])
        self.assertEqual(result['Plans'][0]['Temp Written Blocks'],4)
        self.assertEqual(result['Plans'][0]['Actual Rows'],3)


if __name__=='__main__':unittest.main()
