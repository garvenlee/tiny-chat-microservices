CREATE TABLE IF NOT EXISTS friends (
    seq serial PRIMARY KEY NOT NULL,
    owner_id integer not NULL,
    friend_id integer not NULL,
    -- CREATE INDEX
    session_id bigint NOT NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    remarks varchar(20),
    status relation_status DEFAULT 'Active',
    -- "Deleted", "Blocked"
    CONSTRAINT friends_unique_index UNIQUE (owner_id, friend_id),
    FOREIGN KEY(owner_id) REFERENCES users(seq),
    FOREIGN KEY(friend_id) REFERENCES users(seq)
);