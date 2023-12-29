-- trigger after insert
CREATE OR REPLACE FUNCTION incr_friend_count_when_insert() RETURNS TRIGGER AS $$ BEGIN
UPDATE users
SET friend_count = friend_count + 1
WHERE seq = NEW.owner_id;
RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- 
CREATE TRIGGER incr_friend_count_when_insert_trigger
AFTER
INSERT ON friends FOR EACH ROW EXECUTE FUNCTION incr_friend_count_when_insert();