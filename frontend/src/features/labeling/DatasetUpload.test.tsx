import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { DatasetUpload } from './DatasetUpload';

afterEach(() => vi.restoreAllMocks());

function chooseFile(size: number) {
  render(<MemoryRouter><QueryClientProvider client={new QueryClient()}><DatasetUpload disabled={false} /></QueryClientProvider></MemoryRouter>);
  const file = new File(['fixture'], 'mini.zip', { type: 'application/zip' });
  Object.defineProperty(file, 'size', { value: size });
  fireEvent.change(screen.getByLabelText('원본 데이터 ZIP'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: '데이터셋 업로드' }));
}

it('uploads a mini archive above the former 512MiB limit', async () => {
  const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ datasetId: 7, sceneCount: 10 }), { status: 201 }));
  chooseFile(4_200_000_000);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('10개 씬을 등록했습니다.'));
  expect(request).toHaveBeenCalledWith('/api/dataset-uploads', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }));
});

it('rejects archives over 5GB without starting a request', () => {
  const request = vi.spyOn(globalThis, 'fetch');
  chooseFile(5_000_000_001);
  expect(screen.getByRole('alert')).toHaveTextContent('5GB 이하');
  expect(request).not.toHaveBeenCalled();
});
