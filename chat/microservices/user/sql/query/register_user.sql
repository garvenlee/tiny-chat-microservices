WITH ref AS(
    INSERT INTO users (email, password, username)
    VALUES ($1, $2, $3) ON CONFLICT (email) DO
    UPDATE
    SET username = CASE
            WHEN EXCLUDED.username <> users.username THEN EXCLUDED.username
            ELSE users.username
        END,
        password = CASE
            WHEN EXCLUDED.password <> users.password THEN EXCLUDED.password
            ELSE users.password
        END
    WHERE users.email = EXCLUDED.email
        AND users.confirmed = FALSE
        AND (
            EXCLUDED.username <> users.username
            OR EXCLUDED.password <> users.password
        )
    RETURNING seq,
        confirmed
)
SELECT seq,
    confirmed
FROM ref
UNION ALL
SELECT seq,
    confirmed
FROM users
WHERE email = $1
LIMIT 1;