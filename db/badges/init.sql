DROP TABLE IF EXISTS user_badges CASCADE;
DROP TABLE IF EXISTS badges CASCADE;

CREATE TABLE badges (
    badge_id SERIAL PRIMARY KEY,
    title VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    milestone INTEGER NOT NULL
);

CREATE TABLE user_badges (
    badge_id INTEGER NOT NULL REFERENCES badges(badge_id),
    user_id INTEGER NOT NULL,
    awarded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (badge_id, user_id)
);

