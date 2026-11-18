"""Derive a reviewable comparison from completed S3 Java logs, without rerunning AWS.

Keeps all original files. Each derived file is create-only; use a fresh output
directory after new experiments. Inventory payloads stay local, hashes are public.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET
from measurement import parse_line,summarize


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    read=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
    def save(path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
    cases=[];interrupted=[]
    phases=['pilot','faults','large']+[name for name in ('post-reboot-pair','threshold') if (a.directory/name/'manifest.json').exists()]
    for phase in phases:
        manifest=read(a.directory/phase/'manifest.json')
        if not manifest.get('pass') or not all(c.get('cleaned') for c in manifest['cases']):
            if phase!='large':raise ValueError(phase+' incomplete or unclean')
            recovery=read(a.directory/'reboot-recovery/result.json')
            recovered={c['case'] for c in recovery['cases'] if c.get('cleaned')}
            if not recovery.get('pass'):raise ValueError('Interrupted trial recovery failed')
            for case in manifest['cases']:
                if not case.get('cleaned'):
                    if case['label'] not in recovered:raise ValueError('Unrecovered interrupted case')
                    interrupted.append({'phase':phase,'case':case['label'],'reason':'user-reported GPU issue and host reboot; S3 test had no GPU access',
                                        'excluded_from_timing':True,'recovery':recovery})
        for case in manifest['cases']:
            if not case.get('cleaned'):continue
            source=a.directory/phase/case['label'];destination=a.output/phase/case['label']
            result=read(source/'result.json')
            events=[json.loads(line) for line in (source/'events.jsonl').read_text(encoding='utf-8').splitlines()]
            requests=Counter((r['operation'],r['status']) for r in events if r['event']=='http_attempt')
            if phase=='threshold' and (any(operation=='CreateMultipartUploadRequest' for operation,status in requests)
                                       or not any(operation=='PutObjectRequest' for operation,status in requests)):
                raise ValueError('Automatic small-file case did not use the single PUT path')
            rows=[row for line in (source/'java.stdout.log').read_text(encoding='utf-8').splitlines() if (row:=parse_line(line))]
            save(destination/'normalized-production-log.json',{'events':rows,'summary':summarize(rows)})
            inventory={}
            for name in ('original-files.json','restored-files.json'):
                path=source/name
                if path.exists():
                    payload=read(path);inventory[name]={'entries':len(payload),'bytes':sum(v['bytes'] for v in payload.values()),
                        'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'inventory_content_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
            fault=case['result'].get('fault',case['label'].split('-',2)[-1])
            if fault=='transient503':
                attempts=sum(r.get('operation')=='UploadPartRequest' and r.get('part')==2 for r in events)
                if attempts!=2:raise ValueError('Expected exactly two real part-2 requests for transient retry')
            if fault=='permanent503':
                attempts=sum(r.get('operation')=='UploadPartRequest' and r.get('part')==2 for r in events)
                if attempts!=3 or not any(r.get('result')=='verified_absent' for r in rows):raise ValueError('Permanent failure cleanup gate')
            row={'phase':phase,'case':case['label'],'result':result,'cleaned':True,
                 'http_attempts':[{'operation':operation,'actual_http_status':status,'count':count} for (operation,status),count in sorted(requests.items())],
                 'injections':[r for r in events if r['event'].startswith('injected_')],'inventories':inventory}
            save(destination/'review.json',row);cases.append(row)
    tests=[]
    for directory in sorted(a.directory.glob('java-*-tests*')):
        if not directory.is_dir():continue
        summary=directory/'summary.json';row={'attempt':directory.name,'summary':read(summary) if summary.exists() else None,'failures':[]}
        for path in directory.glob('test-results/*.xml'):
            for case in ET.parse(path).getroot().findall('testcase'):
                for failure in case.findall('failure'):row['failures'].append({'test':case.attrib['name'],'type':failure.attrib.get('type'),'message':failure.attrib.get('message')})
        stderr='\n'.join(path.read_text(encoding='utf-8',errors='replace') for path in directory.glob('*java-tests.stderr.log'))
        row['compiler_diagnostics']=[line for line in stderr.splitlines() if 'error:' in line]
        tests.append(row)
    tests.sort(key=lambda row:(row['summary'] or {}).get('started_at',row['attempt']))
    save(a.output/'test-history.json',tests)
    pairs=[];unpaired=[];paired=[]
    for phase in ('large','post-reboot-pair'):
        large=[c for c in cases if c['phase']==phase]
        for index in range(0,len(large),2):
            group=large[index:index+2]
            pair={c['result']['mode']:c['result'] for c in group}
            if len(group)!=2 or set(pair)!={'single','multipart'}:
                unpaired.extend(group);continue
            paired.extend(group)
            pairs.append({'phase':phase,'pair':index//2,'cases':[c['case'] for c in group],
                          'single_s':pair['single']['upload_s'],'multipart_s':pair['multipart']['upload_s'],
                          'upload_reduction':1-pair['multipart']['upload_s']/pair['single']['upload_s']})
    comparison={}
    for mode in ('single','multipart'):
        rows=[c['result'] for c in paired if c['result']['mode']==mode]
        comparison[mode]={metric:[r[metric] for r in rows] for metric in ('upload_s','download_s','peak_heap_bytes','peak_rss_bytes')}
        comparison[mode]['upload_median_s']=statistics.median(r['upload_s'] for r in rows)
        comparison[mode]['download_median_s']=statistics.median(r['download_s'] for r in rows)
    comparison['upload_reduction']=1-comparison['multipart']['upload_median_s']/comparison['single']['upload_median_s']
    save(a.output/'paired-comparison.json',pairs)
    inventories=[v['inventory_content_sha256'] for case in cases for v in case['inventories'].values()]
    if len(inventories)!=4 or len(set(inventories))!=1:raise ValueError('Full restored inventory differs between modes')
    save(a.output/'summary.json',{'generated_at':datetime.now(timezone.utc).isoformat(),'cases':cases,'large_comparison':comparison,'pairs':pairs,
        'unpaired_observations':unpaired,'interrupted':interrupted,
        'limits':['Two complete pairs before reboot plus a fresh pair after reboot; pooled medians are descriptive only; no p95 or fleet claim',
                  'The third pre-reboot single trial remains an unpaired observation; never match it with a post-reboot candidate',
                  'HTTP 503 and lost acknowledgements are injected after real S3 responses',
                  'SIGKILL cleanup is operator recovery; lifecycle expiration is configured but not observed','RDS/GPU/browser full cycle excluded',
                  'process CPU/peak memory includes verification; first large pair also includes extraction and full file inventory hashing']})
    lines=['# S3 Java 실제 전송·복원 보고서','',f'생성 UTC: {datetime.now(timezone.utc).isoformat()}',
           '', '큰 파일: 4,168,148,189 bytes. 재부팅 전 완결된 2쌍과 재부팅 후 새 1쌍을 구분한다. 재부팅 전 다섯 번째 single은 유효한 단독 관측으로 남기고, 중단된 여섯 번째 multipart는 시간 비교에서 제외한다.',
           '', '| 방식 | 완결된 쌍의 업로드 (초) | 기술 통계 중앙값 | 다운로드 중앙값 |','|---|---|---:|---:|']
    for mode in ('single','multipart'):
        row=comparison[mode];lines.append(f"| {mode} | {', '.join(f'{v:.3f}' for v in row['upload_s'])} | {row['upload_median_s']:.3f}s | {row['download_median_s']:.3f}s |")
    lines+=['',f"업로드 중앙값 감소율: {comparison['upload_reduction']*100:.2f}%. 음수면 후보가 느리다.",
            '각 쌍의 업로드 감소율: '+', '.join(f"{r['phase']} #{r['pair']}: {r['upload_reduction']*100:.2f}%" for r in pairs)+'.',
            '재부팅으로 환경이 분리되었으므로 합친 중앙값을 안정적 개선의 근거로 쓰지 않는다.',
            '완결된 짝이 없는 single 관측: '+', '.join(f"{r['result']['upload_s']:.3f}s" for r in unpaired)+'.',
            '', '모든 완료 다운로드의 SHA-256, 첫 큰 파일 쌍의 전체 복원 inventory, 5종 주입 장애, UUID 객체 버전·미완료 파트 정리를 검증했다.',
            '다운로드 경로는 양쪽에 동일하다. 다운로드 차이를 multipart 업로드 최적화 효과로 해석하지 않는다.',
            '채택 결정·한계·원복·코드 위치는 저장소 docs/s3-java-optimization-2026-11-18.md를 따른다.',
            '', '상세 결과는 summary.json, 단계별 정규화 로그는 각 case 폴더, 초기 컴파일/fixture 실패는 test-history.json에 있다. 원본 stdout/stderr/events/inventory는 상위 원본 폴더에 보존했다.']
    (a.output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
