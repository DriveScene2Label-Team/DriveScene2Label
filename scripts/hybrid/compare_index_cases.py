"""Validate repeated CLIP index experiments and compare vectors and scene rankings."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def database_delta(before,after):
    if 'pg_stat_statements' not in before or 'pg_stat_statements' not in after:
        return {'available':False,'sqlstate':after.get('pg_stat_statements_unavailable_sqlstate',before.get('pg_stat_statements_unavailable_sqlstate')),
                'limitation':'Server counters unavailable; do not claim measured SQL-call reductions from source analysis alone.'}
    original={row['queryid']:row for row in before['pg_stat_statements']};kinds={};reset=False
    for row in after['pg_stat_statements']:
        prior=original.get(row['queryid'],{});calls=row['calls']-prior.get('calls',0)
        if calls<0:reset=True;continue
        value=kinds.setdefault(row['kind'],{'calls':0,'total_exec_time_ms':0.})
        value['calls']+=calls;value['total_exec_time_ms']+=row['total_exec_time_ms']-prior.get('total_exec_time_ms',0)
    return {'available':True,'reset_detected':reset,'by_kind':kinds,
            'limitation':'Database-wide interval counters may include polling or other clients; server execution time excludes network/pool wait.'}


def summarize(path):
    client=read(path/'client-report.json');report=read(path/'report.json');conditions=read(path/'test-conditions.json')
    rows=[json.loads(x) for x in (path/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    clips=[r for r in rows if r['tag']=='CLIP' and str(r.get('dataset'))==str(client['dataset_id'])]
    done=[r for r in rows if r['tag']=='CLIP_INDEX' and r.get('event')=='completed' and str(r.get('dataset'))==str(client['dataset_id'])]
    batches=[r for r in rows if r['tag']=='CLIP_INDEX' and r.get('event')=='batch_loaded' and str(r.get('dataset'))==str(client['dataset_id'])]
    stages=[r for r in rows if r['tag']=='CLIP_STAGE' and r.get('stage')=='image_embed']
    expected=conditions['expected_images'];source='pending_batch' if conditions['mode']=='prefetch' else 'per_image'
    passed=(client['status']=='completed' and len(clips)==len({r['image'] for r in clips})==len(stages)==expected
            and len(done)==1 and all(r['status']=='STORED' and r.get('source')==source for r in clips)
            and len(read(path/'vectors.json')['vectors'])==expected
            and len(read(path/'rankings.json'))==18
            and not report['capture_errors'] and not report['failures'])
    fields=('source_ms','exists_ms','cache_ms','ai_ms','storage_ms','total_ms')
    instances=[json.loads(line) for line in (path/'instances.stdout.log').read_text(encoding='utf-8').splitlines()] if (path/'instances.stdout.log').exists() else []
    return {'directory':str(path),'mode':conditions['mode'],'repeat':conditions['repeat'],'dataset_id':client['dataset_id'],
        'valid':passed,'images':len(clips),'clip_stage_images':len(stages),'source_counts':dict(Counter(r.get('source') for r in clips)),
        'index_wall_seconds':float(done[0]['wall_ms'])/1000 if len(done)==1 else None,
        'client_full_seconds':client.get('total_seconds'),'sums_seconds':{k:sum(float(r.get(k,0)) for r in clips)/1000 for k in fields},
        'image_digests':(path/'images.stdout.log').read_text(encoding='utf-8').strip().splitlines(),
        'backend_instance':instances[0]['id'] if len(instances)==2 else None,
        'ai_instance':instances[1]['id'] if len(instances)==2 else None,
        'pending_queries_observed':len(batches),'pending_jdbc_seconds':sum(float(r.get('jdbc_ms',0)) for r in batches)/1000,
        'database_counters':database_delta(read(path/'db-before.json'),read(path/'vectors.json')),
        'capture_errors':report['capture_errors'],'failed_events':len(report['failures'])}


def vectors_match(a,b):
    left={r['sample_data_token']:json.loads(r['embedding']) for r in a['vectors']}
    right={r['sample_data_token']:json.loads(r['embedding']) for r in b['vectors']}
    result={'same_keys':left.keys()==right.keys(),'same_model':a.get('model')==b.get('model') and a.get('preprocess')==b.get('preprocess'),
            'unique_exports':len(left)==len(a['vectors']) and len(right)==len(b['vectors']),
            'pairs':len(left.keys() & right.keys()),'max_absolute_difference':0.,'min_cosine':1.,'valid_geometry':True,'exact_pairs':0}
    for key in left.keys() & right.keys():
        x,y=left[key],right[key]
        if len(x)!=768 or len(y)!=768 or not all(math.isfinite(v) for v in x+y):result['valid_geometry']=False;continue
        xx=math.fsum(v*v for v in x);yy=math.fsum(v*v for v in y)
        if abs(math.sqrt(xx)-1)>1e-3 or abs(math.sqrt(yy)-1)>1e-3:result['valid_geometry']=False
        cosine=math.fsum(u*v for u,v in zip(x,y))/math.sqrt(xx*yy) if xx*yy>0 else -1
        result['min_cosine']=min(result['min_cosine'],cosine)
        result['max_absolute_difference']=max(result['max_absolute_difference'],max(abs(u-v) for u,v in zip(x,y)))
        result['exact_pairs']+=int(x==y)
    result['passed']=(result['same_keys'] and result['same_model'] and result['unique_exports'] and result['valid_geometry'] and result['pairs']>0
                      and result['max_absolute_difference']<=1e-5 and result['min_cosine']>=0.99999)
    return result


def rankings_match(left,right):
    result={'queries':len(left),'same_order':len(left)==len(right),'same_metadata':True,'finite_scores':True,'nonempty':True,'max_score_difference':0.}
    for a,b in zip(left,right):
        if a['parameters']!=b['parameters'] or [r['sceneToken'] for r in a['response']['scenes']] != [r['sceneToken'] for r in b['response']['scenes']]:result['same_order']=False;continue
        for x,y in zip(a['response']['scenes'],b['response']['scenes']):
            if not math.isfinite(x['score']) or not math.isfinite(y['score']):result['finite_scores']=False
            else:result['max_score_difference']=max(result['max_score_difference'],abs(x['score']-y['score']))
            for field in ('matchedImages','contributingImages','bestSampleToken','bestImagePath','matchScore'):
                if x.get(field)!=y.get(field):result['same_metadata']=False
        if not a['response']['scenes'] or not b['response']['scenes']:result['nonempty']=False
    result['passed']=result['same_order'] and result['same_metadata'] and result['finite_scores'] and result['nonempty'] and result['queries']>0 and result['max_score_difference']<=1e-5
    return result


def runtime_conditions(values):
    images=len({tuple(v['image_digests']) for v in values})==1 and all(len(v['image_digests'])==2 for v in values)
    backends={v['backend_instance'] for v in values if v['backend_instance']}
    ais={v['ai_instance'] for v in values if v['ai_instance']}
    populated=all(v['backend_instance'] and v['ai_instance'] for v in values)
    return {'same_images':images,'distinct_backend_containers':len(backends),'distinct_ai_containers':len(ais),
            'passed':len(values)==6 and images and bool(populated) and len(backends)==6 and len(ais)==1}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    runs=read(a.directory/'runs.json');values=[summarize(Path(r['directory'])) for r in runs];pairs=[]
    for repeat in sorted({r['repeat'] for r in values}):
        modes={r['mode']:r for r in values if r['repeat']==repeat};base,opt=modes['baseline'],modes['prefetch']
        left,right=Path(base['directory']),Path(opt['directory'])
        pairs.append({'repeat':repeat,'baseline':base,'prefetch':opt,
            'vectors':vectors_match(read(left/'vectors.json'),read(right/'vectors.json')),
            'rankings':rankings_match(read(left/'rankings.json'),read(right/'rankings.json')),
            'wall_reduction':1-opt['index_wall_seconds']/base['index_wall_seconds'] if base['valid'] and opt['valid'] else None})
    runtime=runtime_conditions(values);same_images=runtime['same_images'];conditions_passed=runtime['passed']
    passed=(len(values)==6 and len(pairs)==3 and same_images and all(v['valid'] for v in values)
            and all(v['vectors']['passed'] and v['rankings']['passed'] for v in pairs))
    medians={mode:statistics.median(v['index_wall_seconds'] for v in values if v['mode']==mode and v['index_wall_seconds'] is not None) for mode in ('baseline','prefetch')}
    result={'pairs':pairs,'quality_passed':passed,'conditions_passed':conditions_passed,'same_runtime_images':same_images,'index_medians_seconds':medians,
        'runtime_conditions':runtime,
        'median_wall_reduction':1-medians['prefetch']/medians['baseline'],
        'scope':'controlled repeated two-scene keyframe input; upload/S3/import recorded separately from index wall time'}
    result['decision']='eligible_for_full_cycle' if passed and conditions_passed and result['median_wall_reduction']>0 else 'hold'
    (a.directory/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='pairs'}))


if __name__=='__main__':main()
