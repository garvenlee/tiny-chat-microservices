CREATE TABLE IF NOT EXISTS outbox (  -- push model
    channel_id bigint,  -- maybe unnecessary?
    message_id bigint,  -- used to sort messages in database and client UI
    sender_seq bigint,  -- used to filter duplicate messages with sender_id in the server 
    sender_id bigint, -- partition key
    receiver_id bigint,  
    content text,
    PRIMARY KEY (sender_id, message_id)
 ) WITH CLUSTERING ORDER BY (message_id DESC);