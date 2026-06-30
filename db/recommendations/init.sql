DROP TABLE IF EXISTS user_reference_movies CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;

CREATE TABLE user_preferences (
    preference_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    genre_id INTEGER NOT NULL,
    preference_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE user_reference_movies (
    reference_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);
