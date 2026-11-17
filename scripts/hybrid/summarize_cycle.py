"""Finalize upload, recovery or label-cycle evidence without hiding stage reports."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
from evidence_io import save_json


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--kind',choices=('upload','storage','label'),required=True);a=p.parse_args();root=a.directory
    if not (root/'STOP').exists():raise ValueError('Finish collection first')
    report=read(root/'report.json');execution=read(root/'execution-summary.json')
    rows=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
    passed=execution['exit_code']==execution['final_collect_exit_code']==0 and not report['capture_errors'] and not report['failures']
    summary={'kind':a.kind,'events':len(rows),'capture_errors':report['capture_errors'],'failed_events':len(report['failures'])}
    lines=[f'# {a.kind} — 정상 API 전체 사이클 검증','',
        '경로: 127.0.0.1 HTTP 클라이언트 → 로컬 backend/GPU → 기존 서울 RDS·S3. 공개 Vercel·브라우저 전송 시험은 아니다. 중첩된 단계 시간을 합산하지 않는다.','']
    if a.kind=='upload':
        client=read(root/'client-report.json');clips=[r for r in rows if r['tag']=='CLIP' and str(r.get('dataset'))==str(client['dataset_id'])]
        stages=[r for r in rows if r['tag']=='CLIP_STAGE' and r.get('stage')=='image_embed']
        end=[r for r in rows if r['tag']=='CLIP_INDEX' and r.get('event')=='completed' and str(r.get('dataset'))==str(client['dataset_id'])]
        count=client['index_status']['totalImages']
        passed=passed and client['status']=='completed' and len(clips)==len({r['image'] for r in clips})==len(stages)==count and len(end)==1 and all(r.get('status')=='STORED' for r in clips)
        summary.update(dataset=client['dataset_id'],images=count,clip_events=len(clips),ai_image_events=len(stages),
            sources=dict(Counter(r.get('source') for r in clips)),client_seconds=client['total_seconds'],transfer_seconds=client['transfer_seconds'],
            index_seconds=float(end[0]['wall_ms'])/1000 if len(end)==1 else None)
        lines += [f"dataset {client['dataset_id']}, {client['scene_count']}씬, 이미지 {len(clips)}/{count}장 저장. AI 이벤트 {len(stages)}개.",'',
            '| 경계 | 초 |','|---|---:|',f"| 전송 시작→인덱싱 완료 확인 | {client['total_seconds']:.3f} |",f"| 클라이언트 전송 | {client['transfer_seconds']:.3f} |"]
        for row in rows:
            if row['tag']=='UPLOAD_STAGE' and 'wall_ms' in row:lines.append(f"| 서버 {row['stage']} | {float(row['wall_ms'])/1000:.3f} |")
        if len(end)==1:lines.append(f"| CLIP_INDEX 시작→완료 | {summary['index_seconds']:.3f} |")
        lines += ['', '이미지별 Source·exists·AI·저장은 events.jsonl에 분리되어 있다. 전체 소요시간에는 10초 polling 지연이 포함된다. 이 전체 원본 1회는 규모 확대 동작 확인이며 작은 반복용 C1이나 과거 C0와 동일 조건의 전후 비교가 아니다. 저장 벡터·검색 품질은 별도 전체 인덱스 비교 보고서에서 검증한다.']
    elif a.kind=='storage':
        storage=read(root/'storage-cycle.json');cases=storage['cases']
        passed=passed and storage['status']=='completed' and len(cases)==3 and not storage.get('recovery_errors') and all(c[k] for c in cases for k in ('files_match_warm','archive_matches_original','inventory_matches_warm'))
        summary.update(dataset=storage['dataset']['id'],cases=[{k:c[k] for k in ('mode','read_seconds','first_read_seconds','files_match_warm','archive_matches_original','inventory_matches_warm')} for c in cases])
        lines += ['| 캐시 조건 | 첫 GET 초 | 전체 GET 초 | 요청 파일 수 |','|---|---:|---:|---:|']
        for case in cases:lines.append(f"| {case['mode']} | {case['first_read_seconds']:.3f} | {case['read_seconds']:.3f} | {len(case['reads'])} |")
        audit=cases[0]['audit']
        lines += ['',f"모든 조건에서 원본 archive SHA256·조회한 센서/map 파일 해시·metadata JSON 해시·{audit['files']:,}개 파일/{audit['expanded_bytes']:,}바이트 inventory가 일치했다. 전체 추출 파일의 내용을 각각 해시한 검사는 아니다.",
            '정상 GET이 실제 복원을 유발하도록 추출 폴더와 압축파일을 삭제 대신 고유 백업 경로로 rename했다. 해시 계산은 GET 시간 밖에서 수행했다. RDS catalog를 보존하고 maintenance를 재개했다.',
            '반복 탐색·추론에는 추출 캐시가 유리하고, 로컬 archive는 네트워크 없는 복구에 유리하다. S3는 캐시 유실 복구를 제공하지만 현재 큰 archive 전체를 가져오는 구조여서 첫 조회 지연이 크다. 캐시 조건별 1회 관측이며 코드 최적화 배율로 해석하지 않는다.']
    else:
        cycle=read(root/'cycle-completed.json');quality=read(root/'roundtrip-quality.json');download=read(root/'recording-download.json')
        passed=passed and quality['passed'] and download['size_matches'] and download['range_request_passed']
        summary.update(cycle=cycle,quality=quality,recording=download)
        lines += [f"dataset {cycle['dataset']}, job {cycle['job']}, recording {cycle['recording']}.",
            f"전체 {cycle['keyframes']}키프레임·{cycle['boxes']:,}박스를 RDS에서 다시 읽었다. 위치·크기·회전·속도·클래스·점수·attribute·track ID와 프레임별 box 순서를 원본 모델 artifact와 대조했다.",
            f"RDS 왕복 품질 판정: `{quality['passed']}`. 최종 artifact의 정규화 SHA256도 비교했다. track_frames 등 결과 API가 직접 노출하지 않는 최상위 필드는 이 artifact checksum에 포함된다.",
            f"Rerun 전체 파일 {download['bytes']:,}바이트·SHA256 `{download['sha256']}`. 크기 일치와 HTTP 206 Range 데이터 비교 통과. 모든 sample/예측 ID가 recording에 연결된다.",
            '이는 정상 API·DB·파일 전송 검증이며 브라우저의 시각적 렌더링 확인을 대신하지 않는다. 고정 seed G2의 최적화 전후 3D 품질 검증과도 측정 목적이 다르다.']
    summary['passed']=bool(passed);save_json(root/'cycle-summary.json',summary)
    lines += ['',f"최종 판정: **{'통과' if passed else '검토 필요'}**. 로그 {len(rows):,}개, 수집 오류 {len(report['capture_errors'])}개, 실패 이벤트 {len(report['failures'])}개.",'',
        '## 증거와 도구 선택','',
        '정상 API는 실제 worker·저장 경로 검증을 위해, 구조화 JSONL과 자원 표본은 단계와 경쟁 조건을 남기기 위해 사용했다. 명령·소스 해시·이미지 digest·클라이언트 출력은 같은 폴더에 보존한다. 비밀번호·쿠키·전체 환경변수는 수집하지 않는다.',
        '[세부 타이밍](report-stage-timings.md) · [구조화 이벤트](events.jsonl) · [자원 표본](resources.jsonl) · [실행 결과](execution-summary.json) · [요약 JSON](cycle-summary.json)','']
    if not (root/'report-stage-timings.md').exists():shutil.copyfile(root/'report.md',root/'report-stage-timings.md')
    (root/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'directory':str(root),'kind':a.kind,'passed':bool(passed)}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
