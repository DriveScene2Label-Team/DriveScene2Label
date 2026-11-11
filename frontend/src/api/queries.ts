import { queryOptions } from '@tanstack/react-query';
import type {
  CalibratedSensorDto, DatasetDto, EgoPoseDto, GtAnnotationDto, JobResultsDto, JobStatusDto, LabelEditDto, RecordingDto, SampleDetailDto, SampleDto,
  SceneDto, SceneSearchResponseDto,
} from './dto';
import { getJson, qs } from './http';
import {
  gtToBox, toCalibration, toDataset, toEgoPose, toJobResults, toJobStatus, toLabelEdit, toRecording, toSampleFrame, toSampleRef, toScene, toSceneInstances,
  toSearchResult,
} from './mappers';
import type { SampleRef, SensorFile } from './models';

/** Query keys always carry the identifiers that scope the data (numeric ids, never scene names). */
export const qk = {
  datasets: () => ['datasets'] as const,
  scenes: (datasetId: number) => ['scenes', datasetId] as const,
  sceneSamples: (sceneId: number) => ['sceneSamples', sceneId] as const,
  sampleDetail: (sampleId: number) => ['sampleDetail', sampleId, { keyframesOnly: true }] as const,
  annotations: (sampleId: number) => ['annotations', sampleId] as const,
  calibration: (datasetId: number, calibratedSensorToken: string) => ['calibration', datasetId, calibratedSensorToken] as const,
  pose: (sensorFileId: number) => ['pose', sensorFileId] as const,
  search: (p: SearchParams) => ['sceneSearch', p] as const,
  jobStatus: (jobId: number) => ['jobStatus', jobId] as const,
  sceneJobs: (sceneId: number) => ['sceneJobs', sceneId] as const,
  jobResults: (jobId: number) => ['jobResults', jobId] as const,
  recordings: (sceneId: number) => ['recordings', sceneId] as const,
  recording: (recordingId: number) => ['recording', recordingId] as const,
  sceneInstances: (sceneId: number) => ['sceneInstances', sceneId] as const,
  labelEdits: (sceneId: number, jobId: number | null) => ['labelEdits', sceneId, jobId] as const,
};

const STATIC = { staleTime: Infinity, gcTime: 30 * 60_000 } as const;

export const datasetsQuery = () =>
  queryOptions({ queryKey: qk.datasets(), queryFn: ({ signal }) => getJson<DatasetDto[]>('/api/datasets', signal).then((d) => d.map(toDataset)), staleTime: 5 * 60_000 });

export const scenesQuery = (datasetId: number) =>
  queryOptions({
    queryKey: qk.scenes(datasetId),
    queryFn: ({ signal }) => getJson<SceneDto[]>(`/api/datasets/${datasetId}/scenes`, signal).then((d) => d.map(toScene)),
    staleTime: 5 * 60_000,
  });

export const SAMPLE_PAGE = 500;

/** All samples of a scene in time order. Pages through limit=500 until a short page; never stops at the first 100. */
export async function fetchAllSceneSamples(sceneId: number, signal?: AbortSignal): Promise<SampleRef[]> {
  const out: SampleRef[] = [];
  for (let offset = 0; ; offset += SAMPLE_PAGE) {
    const page = await getJson<SampleDto[]>(`/api/scenes/${sceneId}/samples${qs({ limit: SAMPLE_PAGE, offset })}`, signal);
    out.push(...page.map(toSampleRef));
    if (page.length < SAMPLE_PAGE) break;
  }
  return out.sort((a, b) => a.timestampUs - b.timestampUs || a.token.localeCompare(b.token));
}

export const sceneSamplesQuery = (sceneId: number) =>
  queryOptions({ queryKey: qk.sceneSamples(sceneId), queryFn: ({ signal }) => fetchAllSceneSamples(sceneId, signal), ...STATIC });

export const sampleDetailQuery = (sampleId: number) =>
  queryOptions({
    queryKey: qk.sampleDetail(sampleId),
    queryFn: ({ signal }) => getJson<SampleDetailDto>(`/api/samples/${sampleId}${qs({ keyframesOnly: true })}`, signal).then(toSampleFrame),
    ...STATIC,
  });

export const annotationsQuery = (sampleId: number) =>
  queryOptions({
    queryKey: qk.annotations(sampleId),
    queryFn: ({ signal }) => getJson<GtAnnotationDto[]>(`/api/samples/${sampleId}/annotations`, signal).then((d) => d.map(gtToBox)),
    ...STATIC,
  });

/** Calibration is shared by every file of the same calibrated sensor, so it is cached by that token. */
export const calibrationQuery = (datasetId: number, file: SensorFile) =>
  queryOptions({
    queryKey: qk.calibration(datasetId, file.calibratedSensorToken),
    queryFn: ({ signal }) => getJson<CalibratedSensorDto>(`/api/sensor-files/${file.id}/calibration`, signal).then(toCalibration),
    ...STATIC,
  });

/** Ego pose at this file's own timestamp. Each camera uses its own pose. */
export const poseQuery = (file: SensorFile) =>
  queryOptions({
    queryKey: qk.pose(file.id),
    queryFn: ({ signal }) => getJson<EgoPoseDto>(`/api/sensor-files/${file.id}/pose`, signal).then(toEgoPose),
    ...STATIC,
  });

export interface SearchParams {
  q: string;
  datasetId: number | null;
  k: number;
  aggregation: 'TOP_K_AVERAGE';
  imageTopK: number;
  keyframesOnly: boolean;
}

export const searchQuery = (p: SearchParams) =>
  queryOptions({
    queryKey: qk.search(p),
    queryFn: ({ signal }) =>
      getJson<SceneSearchResponseDto>(
        `/api/search/scenes${qs({ q: p.q, k: p.k, datasetId: p.datasetId, aggregation: p.aggregation, imageTopK: p.imageTopK, keyframesOnly: p.keyframesOnly })}`,
        signal,
      ).then(toSearchResult),
    staleTime: 60_000,
    retry: false,
  });

export const sceneJobsQuery = (sceneId: number) =>
  queryOptions({
    queryKey: qk.sceneJobs(sceneId),
    queryFn: ({ signal }) => getJson<JobStatusDto[]>(`/api/auto-label/jobs?sceneId=${sceneId}`, signal).then((jobs) => jobs.map(toJobStatus)),
    staleTime: 5000,
    retry: false,
  });

export const jobStatusQuery = (jobId: number) =>
  queryOptions({
    queryKey: qk.jobStatus(jobId),
    queryFn: ({ signal }) => getJson<JobStatusDto>(`/api/auto-label/jobs/${jobId}`, signal).then(toJobStatus),
    retry: false,
  });

export const jobResultsQuery = (jobId: number) =>
  queryOptions({
    queryKey: qk.jobResults(jobId),
    queryFn: ({ signal }) => getJson<JobResultsDto>(`/api/auto-label/jobs/${jobId}/results`, signal).then(toJobResults),
    staleTime: Infinity,
    gcTime: 10 * 60_000,
    retry: false,
  });

export const recordingsQuery = (sceneId: number) =>
  queryOptions({
    queryKey: qk.recordings(sceneId),
    queryFn: ({ signal }) => getJson<RecordingDto[]>(`/api/scenes/${sceneId}/recordings`, signal).then((d) => d.map(toRecording)),
    retry: false,
  });

export const recordingQuery = (recordingId: number) =>
  queryOptions({
    queryKey: qk.recording(recordingId),
    queryFn: ({ signal }) => getJson<RecordingDto>(`/api/recordings/${recordingId}`, signal).then(toRecording),
    retry: false,
  });

/** GT instance → frames index of a scene. Used for "all frames of this object" counts and timeline marks. */
export const sceneInstancesQuery = (sceneId: number) =>
  queryOptions({
    queryKey: qk.sceneInstances(sceneId),
    queryFn: ({ signal }) => getJson<GtAnnotationDto[]>(`/api/scenes/${sceneId}/annotations`, signal).then(toSceneInstances),
    staleTime: Infinity,
    gcTime: 10 * 60_000,
    retry: false,
  });

/** GT edits of the scene plus prediction edits of the shown job, newest first. */
export const labelEditsQuery = (sceneId: number, jobId: number | null) =>
  queryOptions({
    queryKey: qk.labelEdits(sceneId, jobId),
    queryFn: ({ signal }) => getJson<LabelEditDto[]>(`/api/scenes/${sceneId}/label-edits${qs({ jobId })}`, signal).then((d) => d.map(toLabelEdit)),
    retry: false,
  });
