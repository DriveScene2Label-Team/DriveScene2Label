ALTER TABLE auto_label_job ADD COLUMN source_job_id BIGINT;
ALTER TABLE auto_label_job ADD COLUMN reference_frames JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE auto_label_job ADD CONSTRAINT rigid_source_same_dataset FOREIGN KEY(dataset_id,source_job_id) REFERENCES auto_label_job(dataset_id,id);
ALTER TABLE auto_label_job ADD CONSTRAINT rigid_source_not_self CHECK(source_job_id IS NULL OR source_job_id<>id);
ALTER TABLE auto_label_job ADD CONSTRAINT rigid_refs_object CHECK(jsonb_typeof(reference_frames)='object');
