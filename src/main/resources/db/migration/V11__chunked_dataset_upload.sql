CREATE TABLE dataset_upload_session (
 id UUID PRIMARY KEY,
 filename VARCHAR(255) NOT NULL,
 size_bytes BIGINT NOT NULL CHECK(size_bytes>0 AND size_bytes<=5000000000),
 received_bytes BIGINT NOT NULL DEFAULT 0 CHECK(received_bytes>=0 AND received_bytes<=size_bytes),
 status VARCHAR(16) NOT NULL DEFAULT 'RECEIVING' CHECK(status IN ('RECEIVING','QUEUED','PROCESSING','COMPLETED','FAILED')),
 execution_token UUID,
 dataset_id BIGINT REFERENCES dataset(id),
 error_message TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
