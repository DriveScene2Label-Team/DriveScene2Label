import type {
  CalibratedSensorDto, DatasetDto, EgoPoseDto, GtAnnotationDto, JobResultsDto, JobStatusDto, LabelEditDto, PredictionDto,
  RecordingDto, SampleDetailDto, SampleDto, SceneDto, SceneSearchResponseDto, SensorFileDto,
} from './dto';
import type {
  BoxView, Calibration, Dataset, EgoPose, JobResults, JobStatus, LabelEdit, Recording, SampleFrame, SampleRef, Scene, SceneInstances, SearchResult, SensorFile,
} from './models';
import { classModeFromMapping, gtBaseClass, isClassMode } from '@/lib/classes';
import type { Mat3 } from '@/lib/geometry/transform';

export const CAMERA_CHANNELS = ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'] as const;
export type CameraChannel = (typeof CAMERA_CHANNELS)[number];

export function toDataset(d: DatasetDto): Dataset {
  return { id: d.id, name: d.name, version: d.version, label: `${d.name} · ${d.version}` };
}

export function toScene(s: SceneDto): Scene {
  return { id: s.id, datasetId: s.datasetId, token: s.token, name: s.name, description: s.description, nbrSamples: s.nbrSamples };
}

export function toSampleRef(s: SampleDto): SampleRef {
  return { id: s.id, datasetId: s.datasetId, token: s.token, sceneToken: s.sceneToken, timestampUs: s.timestampUs };
}

export function toSensorFile(f: SensorFileDto): SensorFile {
  return {
    id: f.id, token: f.token, channel: f.channel, modality: f.modality, isKeyFrame: f.isKeyFrame, timestampUs: f.timestampUs,
    width: f.width, height: f.height, calibratedSensorToken: f.calibratedSensorToken, egoPoseToken: f.egoPoseToken,
    vehicle: [f.vehicleX, f.vehicleY, f.vehicleZ], contentUrl: f.contentUrl,
  };
}

/** Keyframe files keyed by channel. If a channel appears twice the closest-to-sample timestamp wins. */
export function toSampleFrame(d: SampleDetailDto): SampleFrame {
  const sample = toSampleRef(d.sample);
  const cameras = new Map<string, SensorFile>();
  let lidar: SensorFile | null = null;
  const closer = (a: SensorFile, b: SensorFile | undefined | null) =>
    !b || Math.abs(a.timestampUs - sample.timestampUs) < Math.abs(b.timestampUs - sample.timestampUs);
  for (const dto of d.sensorFiles) {
    const f = toSensorFile(dto);
    if (f.modality === 'camera') {
      if (closer(f, cameras.get(f.channel))) cameras.set(f.channel, f);
    } else if (f.channel === 'LIDAR_TOP' && closer(f, lidar)) {
      lidar = f;
    }
  }
  return { sample, cameras, lidar, location: d.maps[0]?.location ?? null };
}

export function toCalibration(c: CalibratedSensorDto): Calibration {
  const k = [c.intrinsic00, c.intrinsic01, c.intrinsic02, c.intrinsic10, c.intrinsic11, c.intrinsic12, c.intrinsic20, c.intrinsic21, c.intrinsic22];
  const intrinsic = k.every((v) => typeof v === 'number' && Number.isFinite(v)) ? (k as unknown as Mat3) : null;
  return {
    token: c.token,
    sensorToEgo: {
      translation: [c.translationX, c.translationY, c.translationZ],
      rotation: { w: c.rotationW, x: c.rotationX, y: c.rotationY, z: c.rotationZ },
    },
    intrinsic,
  };
}

export function toEgoPose(p: EgoPoseDto): EgoPose {
  return {
    token: p.token,
    timestampUs: p.timestampUs,
    egoToWorld: { translation: [p.translationX, p.translationY, p.translationZ], rotation: { w: p.rotationW, x: p.rotationX, y: p.rotationY, z: p.rotationZ } },
  };
}

export function gtToBox(a: GtAnnotationDto): BoxView {
  const baseCls = gtBaseClass(a.categoryName);
  const override = a.labelOverride ?? null;
  return {
    key: `GT:${a.datasetId}:${a.sampleToken}:${a.id}`,
    id: a.id, datasetId: a.datasetId, sampleToken: a.sampleToken, source: 'GT', jobId: null,
    label: a.categoryName ?? null, cls: override ?? baseCls, baseCls, edited: override != null && override !== baseCls, categoryToken: a.categoryToken ?? null,
    center: [a.centerX, a.centerY, a.centerZ], sizeWLH: [a.sizeW, a.sizeL, a.sizeH],
    rotation: { w: a.rotationW, x: a.rotationX, y: a.rotationY, z: a.rotationZ }, coordinateFrame: 'WORLD',
    instanceToken: a.instanceToken, numLidarPts: a.numLidarPts, velocityXY: null, attributeName: null,
  };
}

/** Predictions carry no dataset of their own; the results' top-level datasetId applies to all boxes. */
export function predictionToBox(p: PredictionDto, jobId: number, datasetId: number): BoxView {
  return {
    key: `VESPA:${jobId}:${datasetId}:${p.sampleToken}:${p.id}`,
    id: p.id, datasetId, sampleToken: p.sampleToken, source: 'VESPA', jobId,
    label: p.detectionName, cls: p.labelOverride ?? p.detectionName, baseCls: p.detectionName,
    edited: p.labelOverride != null && p.labelOverride !== p.detectionName, categoryToken: null,
    center: [p.centerX, p.centerY, p.centerZ], sizeWLH: [p.sizeW, p.sizeL, p.sizeH],
    rotation: { w: p.rotationW, x: p.rotationX, y: p.rotationY, z: p.rotationZ }, coordinateFrame: 'WORLD',
    instanceToken: null, numLidarPts: null, velocityXY: [p.velocityX, p.velocityY], attributeName: p.attributeName || null, trackId: p.trackId ?? null,
  };
}

/** Integer 0..100 from the server; anything else (missing, null, out of range) is treated as no match score. */
export function toMatchScore(v: unknown): number | null {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 100 ? v : null;
}

export function toSearchResult(r: SceneSearchResponseDto): SearchResult {
  return {
    query: r.query,
    aggregation: r.aggregation,
    hits: r.scenes.map((s) => ({
      sceneId: s.sceneId, datasetId: s.datasetId, sceneToken: s.sceneToken, sceneName: s.sceneName, description: s.description,
      score: s.score, matchScore: toMatchScore(s.matchScore), bestSampleToken: s.bestSampleToken, bestImageId: s.bestImageId, contentUrl: s.contentUrl,
      matchedImages: s.matchedImages, contributingImages: s.contributingImages,
    })),
  };
}

function time(s: string | null | undefined): number | null {
  if (!s) return null;
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : null;
}

export function toJobStatus(j: JobStatusDto): JobStatus {
  const mode = j.classMode ?? classModeFromMapping(j.mappingName);
  return {
    jobId: j.jobId, datasetId: j.datasetId, status: j.status, errorMessage: j.errorMessage,
    createdAt: time(j.createdAt) ?? Date.now(), startedAt: time(j.startedAt), completedAt: time(j.completedAt),
    sceneToken: j.sceneToken ?? null, classMode: isClassMode(mode) ? mode : null, errorCode: j.errorCode ?? null,
  };
}

export function toJobResults(r: JobResultsDto): JobResults {
  const boxesBySample = new Map<string, BoxView[]>();
  for (const token of r.sampleTokens) boxesBySample.set(token, []);
  let boxCount = 0;
  let editedCount = 0;
  for (const p of r.boxes) {
    if (p.deleted) continue; // only present when includeDeleted=true was asked for
    const box = predictionToBox(p, r.jobId, r.datasetId);
    const list = boxesBySample.get(p.sampleToken) ?? [];
    list.push(box);
    boxesBySample.set(p.sampleToken, list);
    boxCount += 1;
    if (box.edited) editedCount += 1;
  }
  return {
    jobId: r.jobId, datasetId: r.datasetId, mappingName: r.mappingName, classMode: classModeFromMapping(r.mappingName),
    sampleTokens: new Set(r.sampleTokens), boxesBySample, boxCount, editedCount, artifactCount: r.artifacts.length,
    artifactPath: r.artifacts[0]?.relativePath ?? null,
  };
}

export function toRecording(r: RecordingDto): Recording {
  return {
    recordingId: r.recordingId, datasetId: r.datasetId, sceneId: r.sceneId, sceneToken: r.sceneToken, jobId: r.jobId,
    status: r.status, sdkVersion: r.sdkVersion, rerunRecordingId: r.rerunRecordingId ?? '', timeline: r.timeline ?? 'sample',
    entities: r.entities ?? { lidar: 'world/lidar', ego: 'world/ego', gt: 'world/gt', prediction: null }, samples: [...(r.samples ?? [])].sort((a, b) => a.index - b.index),
    contentUrl: r.status === 'READY' ? r.contentUrl : null, sizeBytes: r.sizeBytes, errorMessage: r.errorMessage, errorCode: r.errorCode ?? null,
    createdAt: time(r.createdAt) ?? 0,
  };
}

export function toLabelEdit(e: LabelEditDto): LabelEdit {
  return {
    id: e.id, datasetId: e.datasetId, sceneId: e.sceneId, jobId: e.jobId ?? null, targetType: e.targetType, action: e.action, scope: e.scope,
    instanceToken: e.instanceToken ?? null, fromLabel: e.fromLabel, toLabel: e.toLabel ?? null, targetIds: [...(e.targetIds ?? [])],
    sampleTokens: [...(e.sampleTokens ?? [])], count: e.count, createdAt: time(e.createdAt) ?? 0, revertedAt: time(e.revertedAt), revertible: !!e.revertible,
  };
}

/** Scene GT → instanceToken → sample tokens (deleted boxes are not returned by the server). */
export function toSceneInstances(list: GtAnnotationDto[]): SceneInstances {
  const out: SceneInstances = new Map();
  for (const a of list) {
    if (a.deleted || !a.instanceToken) continue;
    const set = out.get(a.instanceToken) ?? new Set<string>();
    set.add(a.sampleToken);
    out.set(a.instanceToken, set);
  }
  return out;
}
