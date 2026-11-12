// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest';
import { uploadChunks } from './chunkedUpload';

afterEach(() => vi.unstubAllGlobals());
it('sends bounded chunks in order and polls registration separately', async () => {
  const storage = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) });
  const file = new File([new Uint8Array(8_000_003)], 'mini.zip');
  const session = { id: '12345678-1234-1234-1234-123456789abc', status: 'RECEIVING', sizeBytes: file.size, receivedBytes: 0, chunkBytes: 4_000_000, workerEnabled: true };
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(session)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...session, status: 'PROCESSING' })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...session, status: 'COMPLETED', datasetId: 12, sceneCount: 10 })))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetch);
  const parts: { path: string; size: number }[] = [];
  vi.stubGlobal('XMLHttpRequest', class {
    path = ''; status = 200; responseText = '{}'; upload = { onprogress: null as ((event: { loaded: number }) => void) | null }; onload: (() => void) | null = null;
    open(_method: string, path: string) { this.path = path; } setRequestHeader() { }
    send(bytes: Blob) { parts.push({ path: this.path, size: bytes.size }); this.upload.onprogress?.({ loaded: bytes.size }); queueMicrotask(() => this.onload?.()); }
  });
  const transferred = vi.fn(); const progress = vi.fn();
  expect(await uploadChunks(file, progress, transferred)).toEqual({ datasetId: 12, sceneCount: 10 });
  expect(parts.map((part) => part.size)).toEqual([4_000_000, 4_000_000, 3]);
  expect(parts.map((part) => part.path.split('offset=')[1])).toEqual(['0', '4000000', '8000000']);
  expect(transferred).toHaveBeenCalledOnce();
  expect(progress).toHaveBeenLastCalledWith(expect.objectContaining({ loaded: file.size, total: file.size }));
  const measurement = JSON.parse(storage.get('ds2l.lastUploadMeasurement')!);
  expect(measurement).toMatchObject({ uploadId: session.id, sentBytes: file.size, resumedBytes: 0, outcome: 'completed' });
  expect(measurement.totalMs).toBeGreaterThanOrEqual(measurement.transferMs);
  expect(measurement.processingMs).toBeGreaterThan(0);
  expect(fetch).toHaveBeenLastCalledWith(`/api/dataset-uploads/sessions/${session.id}/metrics`, expect.objectContaining({ method: 'POST' }));
});
