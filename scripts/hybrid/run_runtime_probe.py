"""Install pinned runtime tools in an experiment-only path and probe the real model.

No pip operation targets the production Python environment. Serialized models,
export failures, provider placement, commands and build times remain evidence.
"""
import argparse
import json
from pathlib import Path
import re
from evidence_io import save_json
from run_grounding_variants import command,read
from run_thread_cases import ROOT,AI


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--dataset-key',required=True)
    p.add_argument('--exporters',nargs='+',choices=('dynamo','legacy','legacy_bool_or'),default=['dynamo','legacy','legacy_bool_or']);a=p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',a.dataset_key):raise ValueError('Expected dataset UUID')
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    remote='/tmp/ds2l-runtime-'+a.directory.name
    output='/results/experiments/'+a.directory.name+'-runtime';deps=output+'/dependencies'
    packages=['numpy==1.26.4','onnx==1.23.2','onnxscript==0.7.2','onnxruntime-gpu==1.32.0']
    plan={'scope':'static real-model compatibility probe; not full pipeline deployment','packages':packages,
        'dependencies_directory':deps,'baseline_versions':'torch 2.14.1+cu130, transformers 4.49.0, numpy 1.26.4',
        'limits':{'export_seconds':600,'ort_seconds':300,'trt_build_and_run_seconds':900,'trt_workspace_bytes':2*1024**3},
        'production_pip_environment_modified':False,'exporters':a.exporters,'cases':[]}
    save_json(a.directory/'runtime-plan.json',plan)
    if command(['docker','exec',AI,'mkdir','-p',remote+'/tools',remote+'/services',output],a.directory,'prepare'):raise RuntimeError('Prepare failed')
    for relative in ('tools/probe_grounding_runtime.py','tools/benchmark_grounding.py','services/grounding_probe.py'):
        if command(['docker','cp',str(ROOT/'ai-server'/relative),AI+':'+remote+'/'+relative],a.directory,'copy-'+Path(relative).stem):raise RuntimeError('Copy failed')
    if command(['docker','exec',AI,'timeout','--kill-after=10s','900s','/opt/vespa-env/bin/python','-m','pip','install','--timeout','30','--retries','2','--target',deps,'--no-compile',*packages],a.directory,'isolated-dependencies'):
        raise RuntimeError('Isolated dependency installation failed; no production environment change')
    environment=['--env','PYTHONPATH='+deps,'--env','HF_HUB_OFFLINE=1','--env','PYTHONUNBUFFERED=1']
    version_code='import torch,transformers,numpy,json,importlib.metadata as m; assert torch.__version__=="2.14.1+cu130" and transformers.__version__=="4.49.0" and numpy.__version__=="1.26.4"; print(json.dumps({n:m.version(n) for n in ("torch","transformers","numpy","onnx","onnxscript","onnxruntime-gpu","protobuf","ml_dtypes")}))'
    if command(['docker','exec',*environment,AI,'/opt/vespa-env/bin/python','-c',version_code],a.directory,'version-check'):raise RuntimeError('Production model dependencies drifted in isolated path')
    if 'legacy_bool_or' in a.exporters:
        code=command(['docker','exec',*environment,AI,'timeout','60s','/opt/vespa-env/bin/python',remote+'/tools/probe_grounding_runtime.py',
                      'adapter_test','--output',output+'/adapter-test'],a.directory,'adapter-test')
        command(['docker','cp',AI+':'+output+'/adapter-test/adapter-test.json',str(a.directory/'adapter-test.json')],a.directory,'copy-adapter-test')
        if code:raise RuntimeError('Small boolean adapter self-test failed; do not run full model')
    successful=None
    for exporter in a.exporters:
        case=a.directory/exporter;case.mkdir(exist_ok=False);target=output+'/'+exporter
        print(json.dumps({'event':'runtime_export_started','exporter':exporter}),flush=True)
        code=command(['docker','exec',*environment,AI,'timeout','--signal=TERM','--kill-after=10s','600s',
                      '/opt/vespa-env/bin/python',remote+'/tools/probe_grounding_runtime.py','export',
                      '--output',target,'--data-root','/uploads/datasets/'+a.dataset_key,'--exporter',exporter],case,'export')
        plan['cases'].append({'phase':'export','exporter':exporter,'exit_code':code,'remote_directory':target})
        for file in ('manifest.json','pytorch-timing.json','export-adapter.json','export-result.json','export-failure.json'):
            command(['docker','cp',AI+':'+target+'/'+file,str(case/file)],case,'copy-'+file)
        save_json(a.directory/'runtime-plan.json',plan)
        if code==0:successful=(case,target);break
    if successful:
        case,target=successful
        code=command(['docker','exec',*environment,AI,'timeout','--signal=TERM','--kill-after=10s','300s',
                      '/opt/vespa-env/bin/python',remote+'/tools/probe_grounding_runtime.py','ort','--output',target],case,'ort')
        plan['cases'].append({'phase':'ort','exit_code':code})
        for file in ('ort-result.json','ort-failure.json'):
            command(['docker','cp',AI+':'+target+'/'+file,str(case/file)],case,'copy-'+file)
        # Install TensorRT only once an actual ONNX graph is available to parse.
        trt_code=command(['docker','exec',AI,'timeout','--kill-after=10s','900s','/opt/vespa-env/bin/python','-m','pip','install','--timeout','30','--retries','2','--target',deps,'--no-compile','tensorrt-cu13==11.4.0.106'],a.directory,'isolated-tensorrt')
        plan['cases'].append({'phase':'trt_dependencies','exit_code':trt_code})
        if trt_code==0:
            code=command(['docker','exec',*environment,AI,'timeout','--signal=TERM','--kill-after=10s','900s',
                          '/opt/vespa-env/bin/python',remote+'/tools/probe_grounding_runtime.py','trt','--output',target],case,'trt')
            plan['cases'].append({'phase':'trt','exit_code':code})
            for file in ('trt-parse.json','trt-build.json','trt-result.json','trt-failure.json'):
                command(['docker','cp',AI+':'+target+'/'+file,str(case/file)],case,'copy-'+file)
    else:
        plan['cases'].append({'phase':'ort_and_trt','status':'not_executed_no_valid_exported_graph'})
    plan['decision']='probe only; production engine, dtype and attention unchanged'
    save_json(a.directory/'runtime-probe-result.json',plan)
    print(json.dumps({'event':'runtime_probe_completed','cases':plan['cases'],'decision':plan['decision']}),flush=True)


if __name__=='__main__':main()
