WITH insertion AS(
    INSERT INTO friends (owner_id, friend_id, session_id)
    SELECT owner_id,
        friend_id,
        session_id
    FROM (
            VALUES (
                    LEAST($1::INTEGER, $2::INTEGER),
                    GREATEST($1::INTEGER, $2::INTEGER),
                    $3::BIGINT
                ),
                (
                    GREATEST($1::INTEGER, $2::INTEGER),
                    LEAST($1::INTEGER, $2::INTEGER),
                    $3::BIGINT
                )
        ) AS data(owner_id, friend_id, session_id) ON CONFLICT ON CONSTRAINT friends_unique_index DO
    UPDATE
    SET status = CASE
            WHEN friends.status <> 'Active' THEN 'Active'
            ELSE friends.status
        END
    WHERE friends.owner_id = EXCLUDED.owner_id
        AND friends.friend_id = EXCLUDED.friend_id
        AND friends.status <> 'Active'
    RETURNING session_id
)
SELECT session_id
FROM insertion
UNION ALL
SELECT session_id
FROM sessions
WHERE lower_id = LEAST($1::INTEGER, $2::INTEGER)
    AND higher_id = GREATEST($1::INTEGER, $2::INTEGER)
LIMIT 1;