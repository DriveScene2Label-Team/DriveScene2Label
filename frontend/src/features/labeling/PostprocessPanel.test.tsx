import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { BoxView, JobResults } from '@/api/models';
import { useWorkspace } from '@/stores/workspace';
import { PostprocessPanel } from './PostprocessPanel';

afterEach(() => { vi.unstubAllGlobals(); useWorkspace.getState().closePane('single'); });
it('selects track zero and retries the same request key while preserving the base result', async () => {
  const box: BoxView = { key: 'base-box', id: 5, datasetId: 9, sampleToken: 'a', source: 'VESPA', jobId: 10, label: 'car', categoryToken: null,
    center: [1, 2, 3], sizeWLH: [2, 4, 1], rotation: { w: 1, x: 0, y: 0, z: 0 }, coordinateFrame: 'WORLD', instanceToken: null, numLidarPts: null, velocityXY: [0, 0], attributeName: null, trackId: 0 };
  const results: JobResults = { jobId: 10, datasetId: 9, mappingName: '8class', classMode: 8, sampleTokens: new Set(['a']), boxesBySample: new Map([['a', [box]]]), boxCount: 1, artifactCount: 1 };
  useWorkspace.getState().openScene('single', { datasetId: 9, sceneId: 4, sampleToken: 'a', jobId: 10 });
  useWorkspace.getState().markDisplayed('single', 'a');
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('lost response')).mockResolvedValueOnce(new Response(JSON.stringify({ jobId: 11 }), { status: 202 }));
  vi.stubGlobal('fetch', fetch);
  render(<PostprocessPanel paneId="single" scene={{ id: 4, datasetId: 9, token: 'scene-token', name: 'scene-0061', description: '', nbrSamples: 1 }}
    samples={[{ id: 1, datasetId: 9, token: 'a', sceneToken: 'scene-token', timestampUs: 0 }]} results={results} disabled={false} />);
  fireEvent.change(screen.getByLabelText('후처리 기준 객체'), { target: { value: 'base-box' } });
  fireEvent.click(screen.getByRole('button', { name: '현재 프레임을 기준으로 추가' }));
  fireEvent.click(screen.getByRole('button', { name: '후처리 결과 생성' }));
  fireEvent.click(await screen.findByRole('button', { name: '같은 후처리 요청 다시 보내기' }));
  await waitFor(() => expect(useWorkspace.getState().panes.single.jobId).toBe(11));
  expect(fetch).toHaveBeenNthCalledWith(1, '/api/auto-label/jobs/10/postprocess', expect.objectContaining({ body: JSON.stringify({ references: { '0': 'a' } }) }));
  const calls = fetch.mock.calls as [string, RequestInit][];
  expect(calls[0]?.[1].headers).toEqual(calls[1]?.[1].headers);
  expect(results.jobId).toBe(10); expect(box.sizeWLH).toEqual([2, 4, 1]);
});
