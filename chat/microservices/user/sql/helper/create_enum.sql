CREATE TYPE request_status AS ENUM (
    'Pending',
    'Accepted',
    'Rejected',
    'Ignored',
    'Revoked'
);
CREATE TYPE relation_status AS ENUM ('Active', 'Deleted', 'Blocked');