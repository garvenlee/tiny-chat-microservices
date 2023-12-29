SELECT seq,
    uid,
    username,
    password,
    confirmed
FROM users
WHERE email = $1;