import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { DatasetUpload } from './DatasetUpload';
import { uploadChunks } from './chunkedUpload';
vi.mock('./chunkedUpload', () => ({ uploadChunks: vi.fn() }));

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function mockUpload() {
  const request = {
    open: vi.fn(), setRequestHeader: vi.fn(), send: vi.fn(),
    upload: { onprogress: null as ((event: ProgressEvent) => void) | null, onload: null as (() => void) | null },
    onload: null as (() => void) | null, onerror: null as (() => void) | null, onabort: null as (() => void) | null,
    status: 201, responseText: JSON.stringify({ datasetId: 7, sceneCount: 10 }),
  };
  vi.stubGlobal('XMLHttpRequest', class { constructor() { return request; } });
  return request;
}

function chooseFile(size: number, name = 'mini.zip') {
  render(<MemoryRouter><QueryClientProvider client={new QueryClient()}><DatasetUpload disabled={false} /></QueryClientProvider></MemoryRouter>);
  const file = new File(['fixture'], name, { type: 'application/zip' });
  Object.defineProperty(file, 'size', { value: size });
  fireEvent.change(screen.getByLabelText('원본 데이터 압축 파일'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '데이터셋 업로드' }));
}

it('tracks multipart transfer separately from server processing and completion', async () => {
  const request = mockUpload();
  chooseFile(4_000_000);
  expect(request.open).toHaveBeenCalledWith('POST', '/api/dataset-uploads');
  expect(request.send).toHaveBeenCalledWith(expect.any(FormData));
  act(() => request.upload.onprogress?.({ lengthComputable: true, loaded: 2_000_000, total: 4_000_000 } as ProgressEvent));
  expect(screen.getByRole('progressbar')).toHaveAttribute('value', '50');
  expect(screen.getByRole('status')).toHaveTextContent('2 / 4 MB');
  act(() => request.upload.onload?.());
  expect(screen.getByRole('status')).toHaveTextContent('파일 전송 완료');
  expect(screen.getByRole('button', { name: '서버 검증 중…' })).toBeDisabled();
  expect(screen.queryByText('10개 씬을 등록했습니다.')).not.toBeInTheDocument();
  act(() => request.onload?.());
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10개 씬을 등록했습니다.'));
  expect(screen.getByRole('link', { name: '씬 열기 · 자동 라벨링' })).toHaveAttribute('href', '/scenes?dataset=7');
});

it('explains a gateway timeout without reporting successful registration', async () => {
  const request = mockUpload();
  request.status = 502;
  request.responseText = 'Bad Gateway';
  chooseFile(4_000_000);
  act(() => request.onload?.());
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('HTTP 502'));
  expect(screen.getByRole('alert')).toHaveTextContent('씬 목록에서 등록 여부');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('rejects archives over 5GB without starting a request', () => {
  const request = mockUpload();
  chooseFile(5_000_000_001);
  expect(screen.getByRole('alert')).toHaveTextContent('5GB 이하');
  expect(request.send).not.toHaveBeenCalled();
});

it('uses resumable chunks for archives larger than one proxy request', async () => {
  vi.mocked(uploadChunks).mockResolvedValue({ datasetId: 8, sceneCount: 10 });
  chooseFile(4_200_000_000);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10개 씬을 등록했습니다.'));
  expect(uploadChunks).toHaveBeenCalledWith(expect.any(File), expect.any(Function), expect.any(Function));
});

it.each(['v1.0-mini.tgz', 'v1.0-mini.tar.gz'])('uploads %s without ZIP conversion', async (name) => {
  vi.mocked(uploadChunks).mockResolvedValue({ datasetId: 8, sceneCount: 10 });
  chooseFile(4_168_148_189, name);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10개 씬을 등록했습니다.'));
  expect(uploadChunks).toHaveBeenCalledWith(expect.objectContaining({ name }), expect.any(Function), expect.any(Function));
});

it('rejects unsupported archives before transmission', () => {
  const request = mockUpload();
  chooseFile(4_200_000_000, 'v1.0-mini.7z');
  expect(screen.getByRole('alert')).toHaveTextContent('ZIP, TGZ 또는 TAR.GZ');
  expect(request.send).not.toHaveBeenCalled();
});
