UPDATE friend_requests
SET status = $1,
    address_at = CURRENT_TIMESTAMP
WHERE friend_requests.request_id = $2
    and friend_requests.address_id = $3
    and friend_requests.status <> $1;