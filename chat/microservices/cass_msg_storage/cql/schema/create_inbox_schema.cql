CREATE TABLE IF NOT EXISTS inbox (  -- push model
    channel_id bigint,  -- maybe unnecessary?
    message_id bigint,  -- used to sort messages in database and client UI
    sender_seq bigint,  -- used to filter duplicate messages with sender_id in the server 
    sender_id bigint, 
    receiver_id bigint,  -- partition key
    content text,
    PRIMARY KEY (receiver_id, message_id)
 ) WITH CLUSTERING ORDER BY (message_id DESC);