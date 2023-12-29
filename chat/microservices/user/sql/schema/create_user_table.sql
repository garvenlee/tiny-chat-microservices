CREATE TABLE IF NOT EXISTS users (
    seq serial PRIMARY KEY,
    uid UUID UNIQUE DEFAULT uuid_generate_v1(),
    -- make it snowflake id
    -- TODO cannot 100% make sure it's unique
    email varchar(30) UNIQUE not NULL,
    password varchar(128) not NULL,
    username varchar(20) not NULL,
    friend_count smallint DEFAULT 0,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP,
    confirmed boolean default FALSE,
    blocked boolean default FALSE
);