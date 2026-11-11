import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { toApiError } from '@/api/http';
import { uploadChunks } from './chunkedUpload';

type UploadedDataset = { datasetId: number; sceneCount: number };
type Transfer = { loaded: number; total: number; bytesPerSecond: number };

function uploadDataset(file: File, progress: (value: Transfer) => void, transferred: () => void): Promise<UploadedDataset> {
  if (file.size > 4_000_000) return uploadChunks(file, progress, transferred);
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const started = Date.now();
    request.open('POST', '/api/dataset-uploads');
    request.setRequestHeader('Accept', 'application/json');
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) progress({ loaded: event.loaded, total: event.total,
        bytesPerSecond: event.loaded / Math.max((Date.now() - started) / 1000, 1) });
    };
    request.upload.onload = transferred;
    request.onerror = () => reject(new Error('업로드 연결이 끊겼습니다. 씬 목록에서 등록 여부를 확인한 뒤 다시 시도해 주세요.'));
    request.onabort = () => reject(new Error('업로드가 중단되었습니다.'));
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try { resolve(JSON.parse(request.responseText) as UploadedDataset); }
        catch { reject(new Error('서버의 업로드 응답을 읽을 수 없습니다. 씬 목록에서 등록 여부를 확인해 주세요.')); }
      } else if (request.status === 502 || request.status === 504) {
        reject(new Error(`서버 응답을 기다리던 연결이 끊겼습니다 (HTTP ${request.status}). 씬 목록에서 등록 여부를 확인해 주세요.`));
      } else {
        void toApiError(new Response(request.responseText, { status: request.status }), '/api/dataset-uploads').then(reject, reject);
      }
    };
    const body = new FormData(); body.append('file', file);
    request.send(body);
  });
}

export function DatasetUpload({ disabled }: { disabled: boolean }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dataset, setDataset] = useState<UploadedDataset | null>(null);
  const [phase, setPhase] = useState<'transfer' | 'processing'>('transfer');
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [phaseStarted, setPhaseStarted] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - phaseStarted) / 1000)), 1000);
    const keepPage = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', keepPage);
    return () => { window.clearInterval(timer); window.removeEventListener('beforeunload', keepPage); };
  }, [busy, phaseStarted]);
  const upload = async () => {
    if (!file) return;
    if (!/\.(zip|tgz|tar\.gz)$/i.test(file.name)) { setError('nuScenes ZIP, TGZ 또는 TAR.GZ 파일을 선택해 주세요.'); return; }
    if (file.size > 5_000_000_000) { setError('5GB 이하의 nuScenes 압축 파일을 선택해 주세요.'); return; }
    setBusy(true); setError(''); setDataset(null);
    setPhase('transfer'); setTransfer(null); setPhaseStarted(Date.now());
    try {
      setDataset(await uploadDataset(file, setTransfer, () => { setPhase('processing'); setPhaseStarted(Date.now()); }));
      void client.invalidateQueries({ queryKey: ['datasets'] });
    } catch (e) { setError(e instanceof Error ? e.message : '데이터셋 업로드에 실패했습니다.'); }
    finally { setBusy(false); }
  };
  return <section className="dataset-upload" aria-label="원본 데이터 업로드">
    <h2>원본 데이터 업로드</h2>
    <p className="muted">nuScenes ZIP · TGZ · TAR.GZ · 최대 5GB</p>
    <p className="small">공식 v1.0-mini.tgz를 그대로 선택하세요. 라벨 파일은 없어도 돼요.</p>
    <input aria-label="원본 데이터 압축 파일" type="file" accept=".zip,.tgz,.tar.gz,application/zip,application/gzip,application/x-gzip" disabled={disabled || busy} onChange={(e) => { setFile(e.currentTarget.files?.[0] ?? null); setError(''); }} />
    <button className="btn primary wide" disabled={!file || disabled || busy} onClick={() => void upload()}>{busy ? (phase === 'transfer' ? '파일 전송 중…' : '서버 검증 중…') : '데이터셋 업로드'}</button>
    {busy && <div role="status">
      {phase === 'transfer' ? <>
        <progress aria-label="파일 전송 진행률" max={100} value={transfer ? Math.floor(transfer.loaded / transfer.total * 100) : 0} />
        <p>파일 전송 {transfer ? Math.floor(transfer.loaded / transfer.total * 100) : 0}%
          {transfer && ` · ${(transfer.loaded / 1_000_000).toFixed(0)} / ${(transfer.total / 1_000_000).toFixed(0)} MB · ${(transfer.bytesPerSecond / 1_000_000).toFixed(1)} MB/s`}</p>
      </> : <p>파일 전송 완료 · 서버에서 파일 검증 및 데이터셋 등록 중입니다.</p>}
      <p>{phase === 'processing' ? '검증 대기' : '전송 경과'} {elapsed}초 · 완료될 때까지 이 페이지를 유지해 주세요.</p>
    </div>}
    {error && <p className="notice notice--err" role="alert">{error}</p>}
    {dataset && <div className="upload-complete" role="status"><p>{dataset.sceneCount}개 씬을 등록했습니다. 씬을 선택해 라벨링을 시작하세요.</p>
      <Link className="btn primary" to={`/scenes?dataset=${dataset.datasetId}`}>씬 목록에서 라벨링하기</Link>
      <p className="muted small">이미지 검색은 자동으로 준비돼요. 준비 중에도 씬을 열 수 있어요.</p>
    </div>}
    <details className="disclosure">
      <summary>지원 파일 · 업로드 도움말</summary>
      <p>압축 해제 후 최대 8GiB. v1.0-mini 또는 v1.0-trainval 메타데이터와 samples/sweeps 센서 파일이 필요해요. 일반 JPG·MP4만으로는 사용할 수 없어요.</p>
      <p>다운로드가 끝난 파일을 선택하세요. 전송이 끊기면 같은 파일을 다시 선택해 이어서 올릴 수 있어요.</p>
    </details>
  </section>;
}
