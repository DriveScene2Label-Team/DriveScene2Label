-- Optional second completed job drawn next to job_id in the same recording (e.g. a VESPA ver2 run), as its own entity.
-- A recording is reused only for the same (job, comparison job) pair.
ALTER TABLE scene_recording ADD COLUMN compare_job_id BIGINT;
ALTER TABLE scene_recording ADD CONSTRAINT scene_recording_compare_job_fk FOREIGN KEY(dataset_id,compare_job_id) REFERENCES auto_label_job(dataset_id,id);
ALTER TABLE scene_recording ADD CONSTRAINT scene_recording_compare_job_check CHECK (compare_job_id IS NULL OR (job_id IS NOT NULL AND compare_job_id<>job_id));
DROP INDEX uq_scene_recording_reuse;
CREATE UNIQUE INDEX uq_scene_recording_reuse ON scene_recording(dataset_id,scene_token,(COALESCE(job_id,0)),(COALESCE(compare_job_id,0)),export_version) WHERE status<>'FAILED';
