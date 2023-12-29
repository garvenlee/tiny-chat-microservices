-- trigger after update
CREATE OR REPLACE FUNCTION modify_friend_count_when_update() RETURNS TRIGGER AS $$ BEGIN IF OLD.status <> 'Deleted'
    AND NEW.status = 'Deleted' THEN
UPDATE users
SET friend_count = friend_count - 1
WHERE seq = NEW.owner_id;
ELSIF OLD.status = 'Deleted'
AND NEW.status = 'Active' THEN
UPDATE users
SET friend_count = friend_count + 1
WHERE seq = NEW.owner_id;
END IF;
RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE TRIGGER modify_friend_count_when_update_trigger 
AFTER
UPDATE OF status ON friends FOR EACH ROW
    WHEN (
        OLD.status IS DISTINCT
        FROM NEW.status
    ) EXECUTE FUNCTION modify_friend_count_when_update();