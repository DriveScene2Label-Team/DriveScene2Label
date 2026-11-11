import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SearchIndexStatus } from './SearchIndexStatus';

afterEach(() => vi.unstubAllGlobals());
it('retries a failed index without discarding stored image progress', async () => {
  const value = { datasetId: 9, status: 'FAILED', indexedImages: 4, totalImages: 10, errorMessage: 'GPU 확인 필요', workerEnabled: true };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(value))).mockResolvedValueOnce(new Response(JSON.stringify({ ...value, status: 'PENDING', errorMessage: null })));
  vi.stubGlobal('fetch', fetch);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SearchIndexStatus datasetId={9} /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '검색 준비 다시 시도' }));
  await waitFor(() => expect(screen.getByRole('progressbar')).toHaveAttribute('value', '4'));
  expect(fetch).toHaveBeenNthCalledWith(2, '/api/datasets/9/search-index', expect.objectContaining({ method: 'POST' }));
});
