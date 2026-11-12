import { isApiError, requestJson, toApiError } from '@/api/http';

export type UploadedDataset = { datasetId: number; sceneCount: number };
export type Transfer = { loaded: number; total: number; bytesPerSecond: number };
type Session = { id: string; status: string; sizeBytes: number; receivedBytes: number; chunkBytes: number; datasetId: number | null; sceneCount: number | null; errorMessage: string | null; workerEnabled: boolean };
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function sendPart(id: string, offset: number, bytes: Blob, progress: (loaded: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `/api/dataset-uploads/sessions/${id}/parts?offset=${offset}`);
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    request.setRequestHeader('Accept', 'application/json');
    request.upload.onprogress = (event) => progress(event.loaded);
    request.onerror = () => reject(new Error('업로드 연결이 끊겼습니다. 같은 파일을 다시 선택하면 이어서 전송할 수 있어요.'));
    request.onabort = () => reject(new Error('업로드가 중단되었습니다. 같은 파일을 다시 선택하면 이어서 전송할 수 있어요.'));
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else void toApiError(new Response(request.responseText, { status: request.status }), 'upload part').then(reject, reject);
    };
    request.send(bytes);
  });
}

export async function uploadChunks(file: File, progress: (value: Transfer) => void, transferred: () => void): Promise<UploadedDataset> {
  const measuredStart = performance.now();
  // Small file fingerprint avoids resuming a different file with the same name/size.
  const fingerprint = new Uint8Array(await new Blob([file.slice(0, 65536), file.slice(-65536)]).arrayBuffer());
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', fingerprint))].map((v) => v.toString(16).padStart(2, '0')).join('');
  const storageKey = `ds2l.upload.${file.size}.${file.lastModified}.${hash}`;
  let session: Session | null = null;
  let previous: string | null = null;
  try { previous = localStorage.getItem(storageKey); } catch { /* Storage is optional. */ }
  if (previous && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(previous)) {
    try { session = (await requestJson<Session>(`/api/dataset-uploads/sessions/${previous}`)).data; }
    catch (error) { if (!isApiError(error) || error.status !== 404) throw error; }
  }
  if (!session) {
    session = (await requestJson<Session>('/api/dataset-uploads/sessions', { method: 'POST', body: { filename: file.name, sizeBytes: file.size } })).data;
    try { localStorage.setItem(storageKey, session.id); } catch { /* In-memory retries still work. */ }
  }
  if (!session.workerEnabled && session.status !== 'COMPLETED') throw new Error('로컬 서버의 업로드 처리 작업자가 꺼져 있습니다. 서버 설정을 확인해 주세요.');
  const started = Date.now();
  const resumed = session.receivedBytes;
  const uploadId = session.id;
  let acknowledged = 0;
  let transferredAt: number | null = null;
  let completed = false;
  try {
  if (session.status === 'RECEIVING') {
    for (let offset = session.receivedBytes; offset < file.size; offset += session.chunkBytes) {
      const bytes = file.slice(offset, Math.min(offset + session.chunkBytes, file.size));
      for (let attempt = 0; ; attempt++) {
        try {
          await sendPart(session.id, offset, bytes, (loaded) => progress({ loaded: offset + Math.min(loaded, bytes.size), total: file.size,
            bytesPerSecond: (offset + loaded - resumed) / Math.max((Date.now() - started) / 1000, 1) }));
          break;
        } catch (error) {
          if (attempt >= 2 || (isApiError(error) && !error.transient)) throw error;
          await delay(1000 * (attempt + 1));
        }
      }
      progress({ loaded: offset + bytes.size, total: file.size, bytesPerSecond: (offset + bytes.size - resumed) / Math.max((Date.now() - started) / 1000, 1) });
      acknowledged += bytes.size;
    }
  }
  transferredAt = performance.now();
  transferred();
  if (['RECEIVING', 'FAILED'].includes(session.status)) session = (await requestJson<Session>(`/api/dataset-uploads/sessions/${session.id}/complete`, { method: 'POST' })).data;
  while (session.status === 'QUEUED' || session.status === 'PROCESSING') {
    await delay(1500);
    session = (await requestJson<Session>(`/api/dataset-uploads/sessions/${session.id}`)).data;
  }
  if (session.status !== 'COMPLETED' || session.datasetId == null || session.sceneCount == null) throw new Error(session.errorMessage || '서버 등록을 마치지 못했습니다. 같은 파일을 다시 선택해서 재시도해 주세요.');
  try { localStorage.removeItem(storageKey); } catch { /* No source bytes are stored in browser storage. */ }
  completed = true;
  return { datasetId: session.datasetId, sceneCount: session.sceneCount };
  } finally {
    const ended = performance.now();
    const metrics = { transferMs: Math.round((transferredAt ?? ended) - measuredStart),
      processingMs: Math.round(transferredAt == null ? 0 : ended - transferredAt), totalMs: Math.round(ended - measuredStart),
      sentBytes: acknowledged, resumedBytes: resumed, outcome: completed ? 'completed' : 'failed' };
    // One compact observation per attempt. Browser times include retries/proxy/polling; they are not wire time.
    try { localStorage.setItem('ds2l.lastUploadMeasurement', JSON.stringify({ uploadId, ...metrics })); } catch { /* Diagnostics are optional. */ }
    console.info('[UPLOAD_CLIENT]', { uploadId, ...metrics });
    void requestJson(`/api/dataset-uploads/sessions/${uploadId}/metrics`, { method: 'POST', body: metrics })
      .catch(() => console.warn('Upload timing delivery failed; the local measurement is still available.'));
  }
}
