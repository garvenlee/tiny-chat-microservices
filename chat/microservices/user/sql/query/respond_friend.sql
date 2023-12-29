UPDATE friends
SET status = $1
WHERE friends.owner_id = $2
    and friends.friend_id = $3
    and friends.status <> $1;