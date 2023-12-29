SELECT
    channel_id, 
    message_id, 
    sender_seq,
    receiver_id, 
    content
FROM chatapp.outbox WHERE sender_id= :sender AND message_id > :msg_id;