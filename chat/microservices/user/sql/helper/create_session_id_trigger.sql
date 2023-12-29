-- trigger after insert
CREATE OR REPLACE FUNCTION create_session_id() RETURNS TRIGGER AS $$ BEGIN IF NEW.owner_id < NEW.friend_id THEN
INSERT INTO sessions (session_id, lower_id, higher_id)
VALUES(NEW.session_id, NEW.owner_id, NEW.friend_id);
END IF;
RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE TRIGGER create_session_id_trigger 
AFTER
INSERT ON friends FOR EACH ROW EXECUTE FUNCTION create_session_id();