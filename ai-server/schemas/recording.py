from typing import Annotated, Literal
from uuid import UUID
import math
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

Size = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Vec3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Quat = tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


def unit(q):
    if abs(math.sqrt(sum(v*v for v in q))-1) > 1e-3:
        raise ValueError("Quaternion W,X,Y,Z must have unit norm")
    return q


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordingLidar(Strict):
    relative_path: str = Field(min_length=1, max_length=1024, description="Relative to the AI server dataset root.")
    sensor_translation: Vec3
    sensor_rotation: Quat
    ego_translation: Vec3
    ego_rotation: Quat
    unit_rotation = field_validator("sensor_rotation", "ego_rotation")(staticmethod(unit))


class RecordingBox(Strict):
    id: int = Field(gt=0)
    center: Vec3
    size_wlh: tuple[Size, Size, Size]
    rotation_wxyz: Quat
    unit_rotation = field_validator("rotation_wxyz")(staticmethod(unit))


class RecordingGtBox(RecordingBox):
    category_name: str | None = Field(default=None, max_length=256)


class RecordingPredictionBox(RecordingBox):
    detection_name: str = Field(min_length=1, max_length=64)


class RecordingSample(Strict):
    index: int = Field(ge=0)
    sample_token: str = Field(min_length=1, max_length=128)
    timestamp_us: int = Field(ge=0)
    lidar: RecordingLidar | None
    gt: list[RecordingGtBox] = []
    predictions: list[RecordingPredictionBox] = []


class RecordingRequest(Strict):
    recording_id: int = Field(gt=0)
    execution_token: UUID
    scene_name: str = Field(pattern=r"^scene-[0-9]{4}$")
    scene_token: str = Field(min_length=1, max_length=128)
    job_id: int | None = Field(default=None, gt=0)
    samples: list[RecordingSample] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def consistent(self):
        if [s.index for s in self.samples] != list(range(len(self.samples))):
            raise ValueError("samples[].index must be 0..n-1 in request order")
        if len({s.sample_token for s in self.samples}) != len(self.samples):
            raise ValueError("samples[].sample_token must be unique")
        if any(a.timestamp_us > b.timestamp_us for a, b in zip(self.samples, self.samples[1:])):
            raise ValueError("samples must be ordered by timestamp_us")
        if self.job_id is None and any(s.predictions for s in self.samples):
            raise ValueError("predictions require job_id")
        return self


class RecordingEntities(BaseModel):
    lidar: Literal["world/lidar"] = "world/lidar"
    ego: Literal["world/ego"] = "world/ego"
    gt: Literal["world/gt"] = "world/gt"
    prediction: Literal["world/prediction"] | None


class RecordingSampleSummary(BaseModel):
    index: int
    sample_token: str
    lidar_points: int = Field(ge=0)
    gt_boxes: int = Field(ge=0)
    prediction_boxes: int = Field(ge=0)


class RecordingResponse(BaseModel):
    recording_id: int
    execution_token: UUID
    relative_path: str = Field(description="Relative to RECORDING_OUTPUT_ROOT; not a download URL.")
    size_bytes: int = Field(gt=0)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 of the .rrd file bytes.")
    sdk_version: str
    export_version: Literal["ds2l-rrd-v2"] = "ds2l-rrd-v2"
    application_id: Literal["drivescene2label"] = "drivescene2label"
    rerun_recording_id: str
    timeline: Literal["sample"] = "sample"
    time_timeline: Literal["timestamp"] = "timestamp"
    entities: RecordingEntities
    samples: list[RecordingSampleSummary]
