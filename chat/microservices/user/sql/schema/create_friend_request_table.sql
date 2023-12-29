CREATE TABLE IF NOT EXISTS friend_requests (
    seq serial PRIMARY KEY NOT NULL,
    request_id integer not NULL,
    address_id integer not NULL,
    -- CREATE INDEX
    request_at timestamp DEFAULT CURRENT_TIMESTAMP,
    address_at timestamp,
    request_msg text,
    status request_status DEFAULT 'Pending',
    -- CREATE INDEX
    CONSTRAINT friend_requests_unique_index UNIQUE (request_id, address_id),
    FOREIGN KEY(request_id) REFERENCES users(seq),
    FOREIGN KEY(address_id) REFERENCES users(seq)
);