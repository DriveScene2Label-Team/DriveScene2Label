# 업로드·라벨 편집·수정본 저장

씬 목록의 **파일 업로드 · 라벨 편집**으로 들어가거나 /labels 를 연다.

## 사용 흐름

1. **라벨 JSON**을 선택하고 **파일 업로드**를 누른다. 업로드 원문과 편집 기준 v0를 별도로 보관한다.
2. 프레임과 박스를 선택한다. 클래스, 중심 XYZ, 크기 W/L/H, 회전 quaternion을 수정한다. 이동 ± 버튼, 회전 ±5°, 박스 추가·삭제를 사용할 수 있다.
3. **수정본 저장**을 누른다. 서버 DB에 v1, v2 …가 추가된다. 원본과 이전 버전은 변경하지 않는다.
4. 저장한 라벨 목록에서 다시 열거나 저장 버전을 바꿀 수 있다.
5. **저장본 vN 다운로드**는 현재 선택한 저장 버전을 내려받는다. 아직 저장하지 않은 화면 편집은 포함하지 않는다. **원본 다운로드**는 업로드한 UTF-8 원문을 돌려준다.
6. 씬 작업대에서 완료된 자동 라벨 결과의 **이 결과 수정 · 저장 · 다운로드**를 누르면 동일 편집기로 연결된다. 원래 predicted_annotation과 GT는 수정하지 않는다.

여러 창에서 같은 문서를 편집하면 먼저 저장한 버전만 반영한다. 나중 요청은 HTTP 409로 충돌을 알려 준다. 데이터는 브라우저 localStorage가 아니라 PostgreSQL/RDS에 저장한다.

## 지원 형식

라벨 JSON은 UTF-8, 최대 20MiB, WORLD 좌표계의 nuScenes/VESPA results 형식이다. 프레임의 마지막 박스를 삭제해도 빈 배열을 유지한다.

~~~json
{
  "coordinate_frame": "WORLD",
  "results": {
    "sample-token": [{
      "sample_token": "sample-token",
      "translation": [1, 2, 3],
      "size": [2, 4, 1.5],
      "rotation": [1, 0, 0, 0],
      "velocity": [0, 0],
      "detection_name": "car",
      "detection_score": 1,
      "attribute_name": ""
    }],
    "empty-sample": []
  }
}
~~~

위치 단위는 m, 크기는 W/L/H, 회전은 W/X/Y/Z 단위 quaternion이다. detection_score는 입력 값을 보존하며 정확도로 표시하지 않는다. 편집 화면은 WORLD XY 위에서 본 평면이다. 카메라 영상 위 드래그 편집은 이번 구현 범위에 포함하지 않는다.

자동 라벨 작업을 불러올 때 v0는 DB에 보관된 예측과 빈 프레임을 복사한 JSON이다. VESPA 원본 파일의 모든 부가 메타데이터를 바이트 그대로 재현하는 기능은 아니다.

## 원본 데이터 ZIP · TGZ

원본 데이터 업로드는 nuScenes ZIP·TGZ·TAR.GZ(최대 5,000,000,000바이트, 압축 해제 후 8GiB)를 지원한다. 라벨 JSON 없이 원본을 업로드하고 씬에서 자동 라벨링을 실행할 수 있다. 압축 파일 최상위에 아래 구조가 있어야 한다. 중간의 nuscenes/ 상위 폴더로 한 번 더 감싸지 않는다.

~~~text
v1.0-mini/           # 또는 v1.0-trainval, 두 버전을 동시에 넣지 않음
  scene.json
  sample.json
  ...               # 기존 importer의 전체 metadata JSON
samples/...
sweeps/...
maps/...
~~~

메타데이터가 참조하는 모든 센서·지도 파일을 포함해야 한다. 기본 압축 해제 제한은 8GiB, 항목 수는 100,000이다. 경로 이탈·중복 파일·누락 파일·관계 오류는 거부하고 해당 업로드를 정리한다. 전체 mini 또는 제한 안에 들어가는 완전한 씬 단위 묶음을 사용한다. 전체 trainval처럼 한도를 넘는 데이터셋의 분할 업로드는 지원하지 않는다.

nuScenes에서 받은 `.tgz`는 그대로 업로드한다. ZIP으로 재압축할 필요가 없다. 실제 파일 헤더로 형식을 판별하며 ZIP 최종 디렉터리와 gzip footer를 검증한다. TAR의 심볼릭 링크·하드 링크·장치 파일·sparse 파일은 허용하지 않는다. 화면은 실제 파일 전송률·전송 속도와 전송 후 서버 검증 대기를 구분한다. 전송 완료가 등록 완료를 뜻하지 않으며, 씬 개수가 표시될 때까지 페이지를 유지한다. 연결 오류 시 같은 원본을 다시 선택하면 조각 전송을 재개한다.

업로드 후 **씬 열기 · 자동 라벨링**에서 씬을 선택한다. AI는 업로드 데이터의 버전·checksum을 확인한 후 기존 VESPA 작업 경로로 실행한다. 업로드 데이터는 local GPU executor만 지원한다. SSH/Slurm으로 파일을 자동 전송하지 않는다.

일반 JPG/MP4만으로 3D 자동 라벨링은 지원하지 않는다. 현재 VESPA에는 nuScenes 센서·pose·calibration·메타데이터가 필요하다. 업로드된 데이터의 CLIP 검색 인덱스는 등록 뒤 자동 생성한다. 업로드 데이터의 Rerun recording 생성은 후속 범위다.

## 저장 위치와 실행

- 라벨 업로드 원문·편집 기준·모든 수정본: PostgreSQL의 label_document, label_revision.
- 원본 압축 파일: UPLOAD_ROOT/archives/<uuid>.zip 또는 <uuid>.tar.gz. TGZ 원본 바이트는 변경하지 않는다.
- 추출된 원본 데이터: UPLOAD_ROOT/datasets/<uuid>/.
- UPLOAD_S3_BUCKET 설정 시: 원본을 S3의 uploads/<uuid>.zip 또는 uploads/<uuid>.tar.gz에 저장한 뒤 dataset을 등록한다. 캐시 복원은 두 형식을 모두 지원한다. 현재 혼합 구성의 backend가 캐시를 준비하고 AI는 공유 볼륨에서 읽는다.
- 로컬 Compose는 uploaded_datasets volume을 공유한다. 호스트에서 직접 실행하면 Spring/AI의 UPLOAD_ROOT를 같은 디렉터리로 설정한다.
- ECS에서는 각 task에 쓰기 가능한 UPLOAD_ROOT와 같은 S3 bucket을 설정한다. 모델 cache와 업로드 cache의 디스크 사용량을 운영 중 관리해야 한다. 자동 캐시 퇴거는 없다.
- S3 저장 실패를 성공 응답으로 바꾸지 않는다. S3 객체 저장 후 DB 등록 실패 시 그 객체를 정리한다. 프로세스가 두 단계 사이에서 종료되면 미참조 객체가 남을 수 있으므로 운영 시 정리 대상이다.

Flyway V7을 적용한다. 기존 migration은 변경하지 않았다. 배포 전 DB backup을 확보하고, 되돌릴 때 label_document/label_revision 데이터를 삭제하지 않는다.

## API

|메서드|경로|기능|
|---|---|---|
|POST|/api/label-documents/upload|multipart file, 선택 datasetId|
|GET|/api/label-documents?page=0|최신순 50개 문서 요약|
|POST|/api/label-documents/from-job/{jobId}|완료 예측의 편집 문서 생성/재사용|
|GET|/api/label-documents/{id}?revision=1|최신 또는 지정 버전|
|GET|/api/label-documents/{id}/revisions|버전·메모·시간 목록|
|POST|/api/label-documents/{id}/revisions|expectedVersion, data, 선택 note로 새 수정본 저장|
|GET|/api/label-documents/{id}/download?revision=1|저장본 JSON 다운로드|
|GET|/api/label-documents/{id}/original|원본 JSON 다운로드|
|POST|/api/dataset-uploads|multipart file로 nuScenes ZIP/TGZ 업로드·검증·등록|
|GET|/api/dataset-uploads/{datasetId}/original|원본 바이트 다운로드, 실제 형식에 맞는 .zip/.tar.gz 파일명|

저장 응답은 {document, revision, data}이며 document.version을 다음 expectedVersion으로 보낸다. document.headRevision은 최신 저장 번호, revision은 현재 조회 번호다. 이전 버전을 열고 저장하면 최신 문서 뒤에 새 버전으로 추가한다. 400은 형식/geometry 오류, 409는 동시 저장 충돌, 413은 크기 제한, 503은 DB/S3/AI 사용 불가다.

## JPA 선택 근거

이번에는 JPA를 선택했다. 문서와 수정 이력을 별도 entity로 관리하고, 일반 CRUD를 repository로 처리하며 문서의 @Version과 수정본 추가를 한 트랜잭션으로 묶기 적합하다. 이는 유지보수 관점의 판단이며 JDBC보다 무조건 빠르다는 뜻은 아니다.

Spring Data JDBC도 @Version과 트랜잭션을 지원한다. 동시 수정 제어 자체가 JPA만 가능한 기능은 아니다. 단순 aggregate 중심 모델이라면 JDBC가 더 단순한 선택일 수 있다. [Spring JDBC persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html), [JPA locking](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/persist/persistence-locking/persistence-locking.html).

일반 catalog repository 5개와 새 라벨 저장을 JPA로 바꿨다. pgvector 검색, metadata batch import, FOR UPDATE SKIP LOCKED 작업 선점은 기존 명시적 SQL/JdbcClient를 유지했다. open-in-view=false, ddl-auto=validate이며 schema 변경은 Flyway가 맡는다. 문서 목록·버전 목록은 payload를 읽지 않는 DTO projection을 사용한다.
