UPDATE users
SET confirmed = true
WHERE seq = $1
    and confirmed = false;