import type { ClassMode, EditAction, EditScope, EditTargetType, JobStatusValue, RecordingStatusValue } from './dto';
import type { Mat3, Pose, Quat, Vec3 } from '@/lib/geometry/transform';

/** Screen models. Built only by mappers.ts; never sent back to the server. */

export interface Dataset {
  id: number;
  name: string;
  version: string;
  label: string;
}

export interface Scene {
  id: number;
  datasetId: number;
  token: string;
  name: string;
  description: string;
  nbrSamples: number;
}

export interface SampleRef {
  id: number;
  datasetId: number;
  token: string;
  sceneToken: string;
  timestampUs: number;
}

export interface SensorFile {
  id: number;
  token: string;
  channel: string;
  modality: string;
  isKeyFrame: boolean;
  timestampUs: number;
  width: number;
  height: number;
  calibratedSensorToken: string;
  egoPoseToken: string;
  vehicle: Vec3;
  contentUrl: string;
}

export interface SampleFrame {
  sample: SampleRef;
  /** Keyed by channel name. Order of the API array is irrelevant. */
  cameras: Map<string, SensorFile>;
  lidar: SensorFile | null;
  location: string | null;
}

export interface Calibration {
  token: string;
  sensorToEgo: Pose;
  /** null when the sensor is not a camera or any intrinsic field is missing. */
  intrinsic: Mat3 | null;
}

export interface EgoPose {
  token: string;
  timestampUs: number;
  egoToWorld: Pose;
}

export type BoxSource = 'GT' | 'VESPA';

/** One box for drawing/listing. Same shape for GT and predictions; `key` is unique per source+frame(+job). */
export interface BoxView {
  key: string;
  id: number;
  datasetId: number;
  sampleToken: string;
  source: BoxSource;
  jobId: number | null;
  /** GT: original nuScenes category (null if the server did not return one). VESPA: detectionName. Never changed by edits. */
  label: string | null;
  /** Class shown in the UI: the edited class when a label edit exists, otherwise `baseCls`. */
  cls: string;
  /** Original class: GT = VESPA 8class comparison class of the category (or the category itself when VESPA does not evaluate it); VESPA = detectionName. */
  baseCls: string;
  /** A label edit changed the class. */
  edited: boolean;
  categoryToken: string | null;
  center: Vec3;
  sizeWLH: Vec3;
  rotation: Quat;
  coordinateFrame: 'WORLD';
  instanceToken: string | null;
  numLidarPts: number | null;
  velocityXY: [number, number] | null;
  attributeName: string | null;
  trackId?: number | null;
  /** Box of the comparison job (pane compareJobId): drawn in its own colour, never selectable or editable. */
  compare?: boolean;
  /** Short name of the comparison job shown in front of its tags (e.g. "ver2-rigid" or "#35"). */
  compareTag?: string;
  /** Comparison box against the shown predictions of the same sample (features/objects/compareBoxes). */
  compareKind?: 'same' | 'changed' | 'added';
}

export interface SearchHit {
  sceneId: number;
  datasetId: number;
  sceneToken: string;
  sceneName: string;
  description: string;
  score: number;
  /** 0..100 calibrated match score, or null (show the raw score instead). */
  matchScore: number | null;
  bestSampleToken: string;
  bestImageId: number;
  contentUrl: string;
  matchedImages: number;
  contributingImages: number;
}

export interface SearchResult {
  query: string;
  aggregation: string;
  hits: SearchHit[];
}

export interface JobStatus {
  jobId: number;
  datasetId: number;
  status: JobStatusValue;
  errorMessage: string | null;
  createdAt: number;
  startedAt: number | null;
  completedAt: number | null;
  /** Present only when the server provides job context (BE-05). */
  sceneToken: string | null;
  classMode: ClassMode | null;
  errorCode: string | null;
  /** Model version suffixes after the commit ("ds2l-p1-p2+ver2-rigid"), "" for plain VESPA, null if unknown. */
  variant: string | null;
}

export interface JobResults {
  jobId: number;
  datasetId: number;
  mappingName: string;
  classMode: ClassMode | null;
  sampleTokens: Set<string>;
  boxesBySample: Map<string, BoxView[]>;
  boxCount: number;
  /** Boxes whose class was changed by a label edit (deleted boxes are not in the results). */
  editedCount: number;
  artifactCount: number;
  artifactPath: string | null;
}

export interface RecordingSample {
  index: number;
  sampleToken: string;
  timestampUs: number;
  lidarPoints: number;
  gtAnnotationIds: number[];
  predictionIds: number[];
}

export interface Recording {
  recordingId: number;
  datasetId: number;
  sceneId: number;
  sceneToken: string;
  jobId: number | null;
  status: RecordingStatusValue;
  sdkVersion: string;
  rerunRecordingId: string;
  timeline: string;
  entities: { lidar: string; ego: string; gt: string; prediction: string | null };
  samples: RecordingSample[];
  contentUrl: string | null;
  sizeBytes: number | null;
  errorMessage: string | null;
  errorCode: string | null;
  createdAt: number;
}

export interface LabelEdit {
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
  createdAt: number;
  revertedAt: number | null;
  revertible: boolean;
}

/** GT instances of a scene: instanceToken → sample tokens where the instance has a (not deleted) box. */
export type SceneInstances = Map<string, Set<string>>;
