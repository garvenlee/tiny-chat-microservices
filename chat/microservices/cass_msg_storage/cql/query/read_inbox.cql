SELECT
    channel_id, 
    message_id, 
    sender_seq,
    sender_id, 
    content
FROM chatapp.inbox WHERE receiver_id = :receiver AND message_id > :msg_id;