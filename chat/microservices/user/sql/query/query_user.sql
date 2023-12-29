SELECT seq,
    uid,
    username,
    confirmed
FROM users
WHERE email = $1;