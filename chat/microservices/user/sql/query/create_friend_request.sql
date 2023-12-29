INSERT INTO friend_requests (request_id, address_id, request_msg)
VALUES ($1, $2, $3) ON CONFLICT ON CONSTRAINT friend_requests_unique_index DO
UPDATE
SET status = CASE
        WHEN friend_requests.status IN ('Rejected', 'Ignored', 'Revoked') THEN 'Pending'
        ELSE friend_requests.status
    END,
    request_msg = CASE
        WHEN friend_requests.request_msg <> EXCLUDED.request_msg THEN EXCLUDED.request_msg
        ELSE friend_requests.request_msg
    END
WHERE friend_requests.status IN ('Rejected', 'Ignored', 'Revoked')
    OR friend_requests.request_msg <> EXCLUDED.request_msg
RETURNING seq;
-- ensure status is Pending