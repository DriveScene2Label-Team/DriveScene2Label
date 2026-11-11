CREATE TABLE dataset_search_index (
 dataset_id BIGINT PRIMARY KEY REFERENCES dataset(id) ON DELETE CASCADE,
 status VARCHAR(16) NOT NULL CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
 execution_token UUID,
 error_message TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
