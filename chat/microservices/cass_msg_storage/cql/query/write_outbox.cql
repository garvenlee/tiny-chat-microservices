INSERT INTO chatapp.outbox (
    channel_id, 
    message_id, 
    sender_seq,
    sender_id, 
    receiver_id, 
    content
) VALUES(?, ?, ?, ?, ?, ?);