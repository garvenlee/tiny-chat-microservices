-- if use transaction, then needs this
WITH ref AS(
    INSERT INTO sessions(lower_id, higher_id)
    VALUES($1, $2) ON CONFLICT on CONSTRAINT sessions_unique_index DO NOTHING
    RETURNING session_id
)
SELECT session_id
FROM ref
UNION ALL
SELECT session_id
FROM sessions
WHERE lower_id = $1
    AND higher_id = $2
LIMIT 1;