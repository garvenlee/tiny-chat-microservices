CREATE TABLE IF NOT EXISTS sessions (
    session_id bigint PRIMARY KEY,
    lower_id integer not NULL,
    higher_id integer not NULL,
    CONSTRAINT sessions_unique_index UNIQUE (lower_id, higher_id)
);