import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { describeError, requestJson } from '@/api/http';
import { systemStatusKey } from '@/api/system';

type IndexStatus = { datasetId: number; status: string; indexedImages: number; totalImages: number; errorMessage: string | null; workerEnabled: boolean };

export function SearchIndexStatus({ datasetId }: { datasetId: number }) {
  const client = useQueryClient();
  const key = ['search-index', datasetId];
  const index = useQuery({ queryKey: key,
    queryFn: async ({ signal }) => (await requestJson<IndexStatus>(`/api/datasets/${datasetId}/search-index`, { signal })).data,
    retry: 1,
    refetchInterval: (query) => query.state.data?.workerEnabled && ['PENDING', 'RUNNING', 'NOT_STARTED'].includes(query.state.data.status) ? 3000 : false,
  });
  const start = useMutation({ mutationFn: async () => (await requestJson<IndexStatus>(`/api/datasets/${datasetId}/search-index`, { method: 'POST' })).data,
    onSuccess: (value) => client.setQueryData(key, value),
  });
  const value = index.data;
  useEffect(() => {
    if (value?.status === 'COMPLETED') void client.invalidateQueries({ queryKey: systemStatusKey(datasetId) });
  }, [value?.status, datasetId, client]);
  if (index.isPending) return <p role="status">검색 준비 상태 확인 중…</p>;
  if (index.isError) return <div className="search-note" role="alert">검색 준비 상태를 읽지 못했어요. {describeError(index.error)} <button className="btn btn--sm btn--weak" onClick={() => void index.refetch()}>다시 확인</button></div>;
  if (!value) return null;
  if (value.status === 'EMPTY') return <p className="help">검색할 카메라 키프레임이 없어요.</p>;
  const active = value.status === 'PENDING' || value.status === 'RUNNING';
  return <div className="search-note" role="status">
    <b>{value.status === 'COMPLETED' ? '검색 준비 완료' : value.status === 'FAILED' ? '검색 준비 실패' : '이미지 검색 준비'}</b>
    <span>{value.indexedImages.toLocaleString('ko-KR')} / {value.totalImages.toLocaleString('ko-KR')}장 · 카메라 키프레임</span>
    {active && <><progress aria-label="검색 인덱스 진행률" value={value.indexedImages} max={value.totalImages} /><span>이미지 검색 준비를 먼저 완료해요. 완료 후 씬에서 라벨 생성 버튼을 직접 눌러 주세요.</span><span>페이지를 닫아도 검색 준비는 계속돼요. 라벨링은 자동으로 시작하지 않아요.</span></>}
    {value.status === 'COMPLETED' && <span>씬을 선택하고 라벨 생성 버튼을 누르면 해당 씬만 처리해요.</span>}
    {value.errorMessage && <span>{value.errorMessage}</span>}
    {!value.workerEnabled && value.status !== 'COMPLETED' && <span>검색 준비 작업자가 꺼져 있어요. 로컬 서버 설정을 확인해 주세요.</span>}
    {['NOT_STARTED', 'FAILED'].includes(value.status) && <button className="btn btn--sm btn--weak" disabled={start.isPending || !value.workerEnabled} onClick={() => start.mutate()}>{start.isPending ? '요청 중…' : value.status === 'FAILED' ? '검색 준비 다시 시도' : '검색 준비 시작'}</button>}
    {start.isError && <span role="alert">{describeError(start.error)}</span>}
  </div>;
}
