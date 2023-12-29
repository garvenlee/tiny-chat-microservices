INSERT INTO chatapp.messages (
    channel_id, 
    bucket, 
    message_id, 
    sender_seq,
    sender_id, 
    receiver_id, 
    content
) VALUES(?, ?, ?, ?, ?, ?, ?);