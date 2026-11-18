"""Resume isolated runtime diagnostics from preserved artifacts, without re-exporting.

Every run has a fresh measurement and output directory. The production Python
environment, weights, engine settings and previous evidence remain unchanged.
"""
import argparse
import json
from pathlib import Path
import re
from evidence_io import save_json
from run_grounding_variants import command
from run_thread_cases import AI, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--reference-run', default='20261117T181902Z')
    parser.add_argument('--phase', choices=('diagnostics', 'detections', 'trt'), required=True)
    parser.add_argument('--dataset-key')
    parser.add_argument('--engine-run', help='Completed TensorRT resume measurement timestamp for six-camera comparison')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / '.local/hybrid/measurements') or not (directory / 'manifest.json').is_file():
        raise ValueError('Begin a fresh local measurement first')
    if not re.fullmatch(r'\d{8}T\d{6}Z', args.reference_run):
        raise ValueError('Expected an existing measurement timestamp')
    if args.phase == 'detections' and not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.dataset_key or ''):
        raise ValueError('Six-camera diagnostics require the cached dataset UUID')
    if args.engine_run and (args.phase != 'detections' or not re.fullmatch(r'\d{8}T\d{6}Z', args.engine_run)):
        raise ValueError('Engine run must be a completed resume timestamp for detection diagnostics')
    parent = '/results/experiments/' + args.reference_run + '-runtime'
    reference = parent + '/legacy_bool_or'
    output = '/results/experiments/' + directory.name + '-resume'
    remote = '/tmp/ds2l-runtime-resume-' + directory.name
    env = ['--env', 'PYTHONPATH=' + parent + '/dependencies', '--env', 'HF_HUB_OFFLINE=1',
           '--env', 'PYTHONUNBUFFERED=1', '--env', 'OMP_NUM_THREADS=1',
           '--env', 'MKL_NUM_THREADS=1', '--env', 'OPENBLAS_NUM_THREADS=1']
    plan = {'phase': args.phase, 'reference': reference, 'output': output,
            'scope': 'one static image/car prompt; no production adoption or full-scene claim',
            'cases': [], 'production_environment_modified': False}
    save_json(directory / 'resume-plan.json', plan)
    if command(['docker', 'exec', AI, 'mkdir', '-p', remote + '/tools', remote + '/services'], directory, 'prepare-tools'):
        raise RuntimeError('Could not prepare isolated tool directory')
    tool = {'diagnostics': 'diagnose_runtime_outputs.py', 'detections': 'benchmark_runtime_detections.py',
            'trt': 'probe_grounding_runtime.py'}[args.phase]
    files = ['tools/' + tool]
    if args.phase == 'detections':
        files += ['tools/benchmark_grounding.py', 'tools/probe_grounding_runtime.py', 'services/grounding_probe.py']
    for relative in files:
        if command(['docker', 'cp', str(ROOT / 'ai-server' / relative), AI + ':' + remote + '/' + relative], directory, 'copy-' + Path(relative).stem):
            raise RuntimeError('Could not copy runtime tool')
    # Fresh root; hard links preserve large model artifacts without rewriting them.
    prepare = r'''
import hashlib,json,os,sys
from pathlib import Path
source=Path(sys.argv[1]);target=Path(sys.argv[2]);phase=sys.argv[3]
if not source.resolve().is_relative_to('/results/experiments') or not target.resolve().is_relative_to('/results/experiments'):
    raise ValueError('Expected results paths')
target.mkdir(parents=True,exist_ok=False)
names=['model.onnx','inputs.npz','reference.npz','manifest.json']
if phase=='trt':
    import onnx
    graph=onnx.load(str(source/'model.onnx'),load_external_data=False)
    for tensor in graph.graph.initializer:
        for item in tensor.external_data:
            if item.key=='location':names.append(item.value)
records=[]
for name in sorted(set(names)):
    path=(source/name).resolve()
    if not path.is_relative_to(source.resolve()) or not path.is_file():raise ValueError('Missing/out-of-scope reference artifact')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    records.append({'file':name,'bytes':path.stat().st_size,'sha256':h.hexdigest()})
    if phase=='trt':
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);os.link(path,dest)
(target/'reference-artifacts.json').write_text(json.dumps(records,indent=2))
print(json.dumps({'artifacts':len(records),'phase':phase}))
'''
    if command(['docker', 'exec', *env, AI, '/opt/vespa-env/bin/python', '-c', prepare,
                reference, output, args.phase], directory, 'prepare-artifacts'):
        raise RuntimeError('Could not validate preserved artifacts')
    command(['docker', 'cp', AI + ':' + output + '/reference-artifacts.json',
             str(directory / 'reference-artifacts.json')], directory, 'copy-reference-artifacts')
    phases = ('cuda', 'cpu') if args.phase == 'diagnostics' else (args.phase,)
    for phase in phases:
        case = directory / phase
        case.mkdir(exist_ok=False)
        if args.phase == 'diagnostics':
            target = output + '/' + phase
            arguments = ['--reference', reference, '--output', target, '--provider', phase]
            files = ('diagnostic.json',)
            timeout = '300s'
        elif args.phase == 'detections':
            target = output + '/six-cameras'
            arguments = ['--reference', reference, '--data-root', '/uploads/datasets/' + args.dataset_key, '--output', target]
            if args.engine_run:
                arguments += ['--runtime', 'trt', '--engine', '/results/experiments/' + args.engine_run + '-resume/model.engine']
            files = ('comparison.json',)
            timeout = '300s'
        else:
            target = output
            arguments = ['trt', '--output', target]
            files = ('trt-parse.json', 'trt-build.json', 'trt-result.json', 'trt-failure.json')
            timeout = '900s'
        print(json.dumps({'event': 'runtime_resume_started', 'phase': phase}), flush=True)
        code = command(['docker', 'exec', *env, AI, 'timeout', '--signal=TERM', '--kill-after=10s', timeout,
                        '/opt/vespa-env/bin/python', remote + '/tools/' + tool, *arguments], case, 'execute')
        plan['cases'].append({'phase': phase, 'exit_code': code, 'remote_directory': target})
        for name in files:
            command(['docker', 'cp', AI + ':' + target + '/' + name, str(case / name)], case, 'copy-' + name)
        save_json(directory / 'resume-plan.json', plan)
        print(json.dumps({'event': 'runtime_resume_finished', 'phase': phase, 'exit_code': code}), flush=True)
    plan['completed'] = all(case['exit_code'] == 0 for case in plan['cases'])
    save_json(directory / 'resume-result.json', plan)
    if not plan['completed']:
        raise RuntimeError('Runtime attempt failed or timed out; inspect preserved logs')


if __name__ == '__main__':
    main()
