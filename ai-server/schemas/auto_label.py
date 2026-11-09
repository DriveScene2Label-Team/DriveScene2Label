from typing import Literal
from uuid import UUID
import math
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, PositiveFloat, model_validator

class AutoLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_name: str = Field(pattern=r"^scene-[0-9]{4}$")
    class_mode: Literal[1, 3, 8] = 8
    job_id: int | None = Field(default=None, gt=0)
    execution_token: UUID | None = None
    dataset_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
    dataset_version: Literal["v1.0-mini", "v1.0-trainval"] | None = None

    @model_validator(mode="after")
    def paired_identity(self):
        if (self.job_id is None) != (self.execution_token is None):
            raise ValueError("job_id and execution_token must be supplied together")
        if (self.dataset_key is None) != (self.dataset_version is None):
            raise ValueError("dataset_key and dataset_version must be supplied together")
        return self

class PredictedBox(BaseModel):
    sample_token: str = Field(min_length=1)
    translation: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    size: tuple[PositiveFloat, PositiveFloat, PositiveFloat]
    rotation: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    velocity: tuple[FiniteFloat, FiniteFloat]
    detection_name: str
    detection_score: FiniteFloat = Field(ge=0, le=1)
    attribute_name: str = ""

    @model_validator(mode="after")
    def valid_geometry(self):
        if not all(math.isfinite(v) for v in self.size) or abs(sum(v*v for v in self.rotation)-1)>0.001:
            raise ValueError("Invalid dimensions or quaternion")
        return self

class AutoLabelResponse(BaseModel):
    run_id: UUID
    scene_name: str
    class_mode: Literal[1, 3, 8]
    job_id: int | None = None
    execution_token: UUID | None = None
    mapping_name: Literal["1class", "3class", "8class"]
    split: str
    coordinate_frame: Literal["WORLD"] = "WORLD"
    score_type: Literal["VESPA_CONSTANT"] = "VESPA_CONSTANT"
    meta: dict[str, bool]
    results: dict[str, list[PredictedBox]]
    artifact_path: str
    result_checksum: str
