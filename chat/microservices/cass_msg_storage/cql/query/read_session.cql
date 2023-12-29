SELECT
    message_id, 
    sender_seq,
    sender_id, 
    content
FROM chatapp.messages WHERE channel_id = :session_id AND bucket = 0 AND message_id > 0;