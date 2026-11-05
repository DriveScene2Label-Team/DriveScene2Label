/**
 * Spring REST DTOs exactly as the server returns them (README_API.md, CatalogController, AutoLabelDtos).
 * Success bodies are plain objects/arrays — there is no `{data}` envelope. Do not reshape here; see mappers.ts.
 */

export interface DatasetDto {
  id: number;
  name: string;
  version: string;
  storageKey: string;
  rootRelativePath: string;
  sourceChecksum: string;
}

export interface SceneDto {
  id: number;
  datasetId: number;
  token: string;
  logToken: string;
  name: string;
  description: string;
  nbrSamples: number;
  firstSampleToken: string;
  lastSampleToken: string;
}

export interface SampleDto {
  id: number;
  datasetId: number;
  token: string;
  sceneToken: string;
  timestampUs: number;
  prevToken: string | null;
  nextToken: string | null;
}

export interface SensorFileDto {
  id: number;
  token: string;
  channel: string;
  modality: string;
  relativePath: string;
  timestampUs: number;
  isKeyFrame: boolean;
  width: number;
  height: number;
  egoPoseToken: string;
  calibratedSensorToken: string;
  vehicleX: number;
  vehicleY: number;
  vehicleZ: number;
  contentUrl: string;
}

export interface MapViewDto {
  id: number;
  token: string;
  relativePath: string;
  location: string;
  contentUrl: string;
}

export interface SampleDetailDto {
  sample: SampleDto;
  sensorFiles: SensorFileDto[];
  maps: MapViewDto[];
}

/** GT box. categoryToken/categoryName are the nullable BE-02 additions (original nuScenes category). */
export interface GtAnnotationDto {
  id: number;
  datasetId: number;
  token: string;
  sampleToken: string;
  instanceToken: string;
  visibilityToken: string | null;
  centerX: number;
  centerY: number;
  centerZ: number;
  sizeW: number;
  sizeL: number;
  sizeH: number;
  rotationW: number;
  rotationX: number;
  rotationY: number;
  rotationZ: number;
  numLidarPts: number;
  numRadarPts: number;
  prevToken: string | null;
  nextToken: string | null;
  categoryToken?: string | null;
  categoryName?: string | null;
  /** Class set by a label edit; null/absent = unchanged (older servers do not send it). */
  labelOverride?: string | null;
  /** True only when deleted rows were requested (includeDeleted=true). */
  deleted?: boolean;
}

export interface CalibratedSensorDto {
  id: number;
  datasetId: number;
  token: string;
  sensorToken: string;
  translationX: number;
  translationY: number;
  translationZ: number;
  rotationW: number;
  rotationX: number;
  rotationY: number;
  rotationZ: number;
  intrinsic00: number | null;
  intrinsic01: number | null;
  intrinsic02: number | null;
  intrinsic10: number | null;
  intrinsic11: number | null;
  intrinsic12: number | null;
  intrinsic20: number | null;
  intrinsic21: number | null;
  intrinsic22: number | null;
}

export interface EgoPoseDto {
  id: number;
  datasetId: number;
  token: string;
  timestampUs: number;
  translationX: number;
  translationY: number;
  translationZ: number;
  rotationW: number;
  rotationX: number;
  rotationY: number;
  rotationZ: number;
}

export interface SceneSearchResultDto {
  sceneId: number;
  datasetId: number;
  sceneToken: string;
  sceneName: string;
  description: string;
  score: number;
  distance: number;
  matchedImages: number;
  contributingImages: number;
  bestImageId: number;
  bestSampleToken: string;
  bestImagePath: string;
  contentUrl: string;
}

export interface SceneSearchResponseDto {
  query: string;
  modelName: string;
  preprocess: string;
  aggregation: string;
  imageTopK: number;
  keyframesOnly: boolean;
  scenes: SceneSearchResultDto[];
}

export type JobStatusValue = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ClassMode = 1 | 3 | 8;

export interface CreateJobRequestDto {
  sceneToken: string;
  datasetId: number;
  classMode: ClassMode;
}

export interface CreatedJobDto {
  jobId: number;
  status: JobStatusValue;
}

/** sceneToken/sceneId/sceneName/classMode/mappingName are BE-05 additions; older servers omit them. */
export interface JobStatusDto {
  jobId: number;
  datasetId: number;
  status: JobStatusValue;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  sceneToken?: string | null;
  sceneId?: number | null;
  sceneName?: string | null;
  classMode?: number | null;
  mappingName?: string | null;
  /** Stable failure identifier (V6+). null for running/completed jobs and rows written before it existed. */
  errorCode?: string | null;
}

export interface PredictionDto {
  id: number;
  sampleToken: string;
  boxIndex: number;
  detectionName: string;
  centerX: number;
  centerY: number;
  centerZ: number;
  sizeW: number;
  sizeL: number;
  sizeH: number;
  rotationW: number;
  rotationX: number;
  rotationY: number;
  rotationZ: number;
  velocityX: number;
  velocityY: number;
  /** VESPA constant 1.0 (scoreType=VESPA_CONSTANT). Never shown as confidence. */
  detectionScore: number;
  attributeName: string;
  /** Class set by a label edit; null/absent = detectionName unchanged. */
  labelOverride?: string | null;
  deleted?: boolean;
}

export interface ArtifactDto {
  id: number;
  artifactType: string;
  storageKey: string;
  /** Storage-relative path. Not a download URL. */
  relativePath: string;
  checksum: string | null;
  contentType: string | null;
}

export interface JobResultsDto {
  jobId: number;
  datasetId: number;
  mappingName: string;
  coordinateFrame: string;
  scoreType: string;
  sampleTokens: string[];
  boxes: PredictionDto[];
  artifacts: ArtifactDto[];
}

export type RecordingStatusValue = 'PENDING' | 'RUNNING' | 'READY' | 'FAILED';

export interface RecordingCreatedDto {
  recordingId: number;
  status: RecordingStatusValue;
  reused: boolean;
}

export interface RecordingSampleDto {
  index: number;
  sampleToken: string;
  timestampUs: number;
  lidarPoints: number;
  gtAnnotationIds: number[];
  predictionIds: number[];
}

export interface RecordingDto {
  recordingId: number;
  datasetId: number;
  sceneId: number;
  sceneToken: string;
  sceneName: string;
  jobId: number | null;
  status: RecordingStatusValue;
  sdkVersion: string;
  exportVersion: string;
  coordinateFrame: string;
  /** AI-derived fields are null until the recording is READY. */
  applicationId: string | null;
  rerunRecordingId: string | null;
  timeline: string | null;
  timeTimeline: string | null;
  entities: { lidar: string; ego: string; gt: string; prediction: string | null } | null;
  /** Omitted (or empty) in list responses and before READY. */
  samples?: RecordingSampleDto[] | null;
  contentUrl: string | null;
  sizeBytes: number | null;
  errorMessage: string | null;
  errorCode?: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}

/** Business error body. Spring default errors ({status,error,path}) are also possible. */
export interface ApiErrorBody {
  code?: string;
  message?: string;
  error?: string;
  status?: number;
  path?: string;
}

export type CapabilityState = 'READY' | 'CONFIGURED' | 'UNAVAILABLE' | 'UNKNOWN';
export type DataOrigin = 'SYNTHETIC' | 'NUSCENES' | 'UNKNOWN';

export interface CapabilityDto {
  state: CapabilityState;
  canExecute: boolean;
  reasonCode: string | null;
  message: string | null;
  checkedAt: string | null;
  expiresAt: string | null;
  executor?: string | null;
}

/** GET /api/system/status (schemaVersion 1). */
export interface SystemStatusDto {
  schemaVersion: number;
  instanceId: string;
  checkedAt: string;
  dataset: { id: number; version: string; origin: DataOrigin; metadataChecksum: string; mediaValidation: string } | null;
  capabilities: Record<'catalog' | 'media' | 'search' | 'vespa' | 'recording', CapabilityDto>;
}

/** Label edit history entry (PATCH/DELETE /api/annotations|auto-label/predictions, GET /api/scenes/{id}/label-edits). */
export type EditTargetType = 'ANNOTATION' | 'PREDICTION';
export type EditAction = 'RENAME' | 'DELETE';
export type EditScope = 'SAMPLE' | 'INSTANCE';

export interface LabelEditDto {
  id: number;
  datasetId: number;
  sceneId: number;
  jobId: number | null;
  targetType: EditTargetType;
  action: EditAction;
  scope: EditScope;
  instanceToken: string | null;
  fromLabel: string;
  toLabel: string | null;
  targetIds: number[];
  sampleTokens: string[];
  count: number;
  createdAt: string;
  revertedAt: string | null;
  revertible: boolean;
}

export interface EditResultDto {
  edit: LabelEditDto;
}
