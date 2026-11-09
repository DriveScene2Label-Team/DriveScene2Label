import { useState } from 'react';
import { Link } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { toApiError } from '@/api/http';

export function DatasetUpload({ disabled }: { disabled: boolean }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dataset, setDataset] = useState<{ datasetId: number; sceneCount: number } | null>(null);
  const upload = async () => {
    if (!file) return;
    if (file.size > 5_000_000_000) { setError('5GB 이하의 nuScenes ZIP을 선택해 주세요.'); return; }
    setBusy(true); setError(''); setDataset(null);
    try {
      const body = new FormData(); body.append('file', file);
      const response = await fetch('/api/dataset-uploads', { method: 'POST', body });
      if (!response.ok) throw await toApiError(response, '/api/dataset-uploads');
      setDataset(await response.json() as { datasetId: number; sceneCount: number });
      void client.invalidateQueries({ queryKey: ['datasets'] });
    } catch (e) { setError(e instanceof Error ? e.message : '데이터셋 업로드에 실패했습니다.'); }
    finally { setBusy(false); }
  };
  return <section className="labels-dataset-upload">
    <h2>원본 데이터 업로드</h2>
    <p className="note">nuScenes ZIP · 최대 5GB, 압축 해제 후 8GiB. 최상위에 v1.0-mini 또는 v1.0-trainval 메타데이터와 해당 samples/sweeps 파일이 필요합니다.</p>
    <p className="note">라벨 JSON은 없어도 됩니다. 원본 ZIP을 올리고 씬을 열어 자동 라벨링을 실행하세요.</p>
    <p className="note">일반 JPG·MP4만으로는 3D 자동 라벨링을 할 수 없습니다. 카메라 보정·센서·위치 정보가 필요합니다.</p>
    <input aria-label="원본 데이터 ZIP" type="file" accept=".zip,application/zip" disabled={disabled || busy} onChange={(e) => { setFile(e.currentTarget.files?.[0] ?? null); setError(''); }} />
    <button className="btn btn--weak" disabled={!file || disabled || busy} onClick={() => void upload()}>{busy ? '업로드·검증 중…' : '데이터셋 업로드'}</button>
    {error && <p className="labels-error" role="alert">{error}</p>}
    {dataset && <div role="status"><p>{dataset.sceneCount}개 씬을 등록했습니다.</p>
      <Link className="btn btn--primary" to={`/scenes?dataset=${dataset.datasetId}`}>씬 열기 · 자동 라벨링</Link>
      <a className="btn btn--weak" href={`/api/dataset-uploads/${dataset.datasetId}/original`}>원본 ZIP 다운로드</a>
    </div>}
  </section>;
}
