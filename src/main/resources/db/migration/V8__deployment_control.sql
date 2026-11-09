CREATE TABLE deployment_control (
 id INTEGER PRIMARY KEY CHECK (id=1),
 maintenance BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO deployment_control(id,maintenance) VALUES(1,FALSE);
