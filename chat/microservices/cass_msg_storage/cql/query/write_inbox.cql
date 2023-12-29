INSERT INTO chatapp.inbox (
    channel_id, 
    message_id, 
    sender_seq,
    sender_id, 
    receiver_id, 
    content
) VALUES(?, ?, ?, ?, ?, ?);