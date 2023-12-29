SELECT u.seq,
    u.uid,
    u.email,
    u.username,
    f.session_id,
    f.remarks
FROM users u
    JOIN (
        SELECT owner_id,
            friend_id,
            session_id,
            remarks
        FROM friends
        WHERE owner_id = $1
    ) f ON u.seq = CASE
        WHEN f.owner_id = $1 THEN f.friend_id
        ELSE f.owner_id
    END;