CREATE TABLE IF NOT EXISTS messages (  -- pull model
    channel_id bigint,  -- snowflake Friend->session_id / Group->group_id
    bucket int,
    message_id bigint,  -- snowflake
    sender_seq bigint,  -- local_id created in the front before sent
    sender_id bigint,
    receiver_id bigint,  -- maybe unnecessary
    content text,
    PRIMARY KEY ((channel_id, bucket), message_id)
    -- (channel_id, bucket) is used to decide the partition
    -- message_id is used to cluster in one partition
 ) WITH CLUSTERING ORDER BY (message_id DESC);