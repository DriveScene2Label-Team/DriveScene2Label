"""Run the packaged read-only JDBC experiment without starting application workers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import textwrap
from evidence_io import save_json

ROOT=Path(__file__).resolve().parents[2]


def summarize_plan(node):
    keys=('Node Type','Join Type','Relation Name','Index Name','Plan Rows','Actual Rows','Actual Loops',
          'Shared Hit Blocks','Shared Read Blocks','Temp Read Blocks','Temp Written Blocks','Sort Method','Sort Space Used','Sort Space Type')
    result={k:node[k] for k in keys if k in node}
    if 'Plans' in node:result['Plans']=[summarize_plan(p) for p in node['Plans']]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--env-file',type=Path,required=True);p.add_argument('--dataset-id',type=int,default=21);a=p.parse_args()
    directory=a.directory.resolve()
    if not (directory/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    source=ROOT/'src/main/java/com/example/demo/nuscenes/repository/SceneSearchRepository.java'
    content=source.read_text(encoding='utf-8');matches=re.findall(r'jdbc\.sql\("""\s*\n(.*?)"""\)',content,re.S)
    if len(matches)!=1:raise ValueError('Expected one exact search SQL text block')
    sql=textwrap.dedent(matches[0]);(directory/'search-baseline.sql').write_text(sql,encoding='utf-8')
    save_json(directory/'query-source.json',{'repository_file':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'sql_sha256':hashlib.sha256(sql.encode()).hexdigest(),'only_change':'distances CTE AS MATERIALIZED',
        'gate':'all ordered fields identical; inspect client/server time and temp I/O; no automatic deployment'})
    name='ds2l-query-'+directory.name.lower()
    command=['docker','compose','--env-file',str(a.env_file),'-f','compose.hybrid.yml','-f','compose.gpu.yml','-f','compose.hybrid-auth.yml',
             'run','--rm','--no-deps','--name',name,'--entrypoint','java','-v',str(directory)+':/evidence','backend',
             '-Dloader.main=com.example.demo.nuscenes.benchmark.QueryExperiment','-cp','/app/app.jar',
             'org.springframework.boot.loader.launch.PropertiesLauncher',str(a.dataset_id),'/evidence/search-baseline.sql','/evidence/query-output']
    save_json(directory/'jdbc-command.json',command)
    with (directory/'jdbc.stdout.log').open('wb') as out,(directory/'jdbc.stderr.log').open('wb') as err:
        result=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err)
    save_json(directory/'jdbc-execution.json',{'exit_code':result.returncode})
    if result.returncode:raise RuntimeError('JDBC experiment failed; source, command and logs retained')
    output=directory/'query-output';read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    completion=read(output/'completion.json');runs=read(output/'runs.json');checks=read(output/'quality-checks.json')
    if not completion['exact_results'] or len(checks)!=54 or len(runs)!=108:raise RuntimeError('Query quality/coverage gate failed')
    scenarios=[]
    for scenario in sorted({r['scenario'] for r in runs}):
        row={'scenario':scenario,'modes':{}}
        for mode in ('baseline','materialized'):
            values=[r['client_seconds'] for r in runs if r['scenario']==scenario and r['mode']==mode]
            if len(values)!=3:raise ValueError('Incomplete paired repetitions')
            plan=read(output/(scenario+'-'+mode+'-plan.json'))[0]
            row['modes'][mode]={'client_median_seconds':statistics.median(values),'client_seconds':values,
                 'server_execution_ms':plan['Execution Time'],'server_planning_ms':plan['Planning Time'],'plan':summarize_plan(plan['Plan'])}
        row['client_reduction']=1-row['modes']['materialized']['client_median_seconds']/row['modes']['baseline']['client_median_seconds']
        scenarios.append(row)
    save_json(directory/'query-comparison.json',{'scope':'exact read-only SQL on three stored image-query fixtures; paired 3 repeats/scenario; not text model inference',
        'quality_passed':True,'pairs':len(checks),'scenarios':scenarios,'decision':'inspect workload-specific timing and temp I/O before any production SQL change',
        'raw_plans':'query-output/*-plan.json retained locally; may contain query vector literals; excluded from Git'})
    print(json.dumps({'quality_passed':True,'pairs':len(checks),'scenarios':len(scenarios)}),flush=True)


if __name__=='__main__':main()
