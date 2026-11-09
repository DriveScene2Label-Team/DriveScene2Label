import { getJson, requestJson, toApiError } from './http';

export interface LabelBox {
  sample_token: string;
  detection_name: string;
  translation: [number, number, number];
  size: [number, number, number];
  rotation: [number, number, number, number];
  velocity: [number, number];
  detection_score: number;
  attribute_name: string;
  [key: string]: unknown;
}
export interface LabelData {
  coordinate_frame: 'WORLD';
  results: Record<string, LabelBox[]>;
  [key: string]: unknown;
}
export interface LabelSummary {
  id: number;
  name: string;
  datasetId: number | null;
  sourceJobId: number | null;
  sourceType: 'UPLOAD' | 'AUTO_LABEL';
  headRevision: number;
  version: number;
  createdAt: string;
}
export interface LabelDetail { document: LabelSummary; revision: number; data: LabelData }
export interface LabelRevision { number: number; note: string; createdAt: string }

export const listLabels = (page = 0) => getJson<LabelSummary[]>(`/api/label-documents?page=${page}`);
export const getLabel = (id: number, revision?: number) => getJson<LabelDetail>(`/api/label-documents/${id}${revision == null ? '' : `?revision=${revision}`}`);
export const labelHistory = (id: number) => getJson<LabelRevision[]>(`/api/label-documents/${id}/revisions`);
export const labelsFromJob = async (id: number) => (await requestJson<LabelDetail>(`/api/label-documents/from-job/${id}`, { method: 'POST' })).data;
export const saveLabel = async (id: number, expectedVersion: number, data: LabelData, note: string) =>
  (await requestJson<LabelDetail>(`/api/label-documents/${id}/revisions`, { method: 'POST', body: { expectedVersion, data, note } })).data;
export async function uploadLabels(file: File, datasetId?: number): Promise<LabelDetail> {
  const body = new FormData(); body.append('file', file);
  if (datasetId != null) body.append('datasetId', String(datasetId));
  const path = '/api/label-documents/upload';
  const response = await fetch(path, { method: 'POST', body });
  if (!response.ok) throw await toApiError(response, path);
  return response.json() as Promise<LabelDetail>;
}
