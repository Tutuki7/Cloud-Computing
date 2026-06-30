DROP TABLE IF EXISTS rating_topics CASCADE;
DROP TABLE IF EXISTS review_sentiment CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS genre_family_members CASCADE;
DROP TABLE IF EXISTS genre_families CASCADE;
DROP TABLE IF EXISTS user_reference_movies CASCADE;
DROP TABLE IF EXISTS user_preferences CASCADE;
DROP TABLE IF EXISTS user_sessions CASCADE;
DROP TABLE IF EXISTS user_oauth CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS watchlist_movies CASCADE;
DROP TABLE IF EXISTS watchlists CASCADE;
DROP TABLE IF EXISTS user_badges CASCADE;
DROP TABLE IF EXISTS badges CASCADE;
DROP TABLE IF EXISTS fraud_alerts CASCADE;
DROP TABLE IF EXISTS movie_cast CASCADE;
DROP TABLE IF EXISTS ratings CASCADE;
DROP TABLE IF EXISTS movie_genres CASCADE;
DROP TABLE IF EXISTS genres CASCADE;
DROP TABLE IF EXISTS movies CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password VARCHAR(255),
    gender VARCHAR(10),
    age INTEGER,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE user_oauth (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    provider VARCHAR(50) NOT NULL,
    provider_id VARCHAR(255) NOT NULL,
    refresh_token VARCHAR(255),
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE user_sessions (
    session_id SERIAL PRIMARY key,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    refresh_token VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE movies (
    movie_id SERIAL PRIMARY KEY,
    movie_title VARCHAR(255) NOT NULL,
    description TEXT,
    imdb_url TEXT,
    release_year INTEGER CHECK (release_year >= 1874),
    runtime INTEGER,
    parental_rating VARCHAR(20),
    poster_url TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    avg_rating numeric(3, 2) DEFAULT NULL
);

CREATE TABLE genres (
    genre_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE movie_genres (
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE movie_cast (
    cast_id SERIAL PRIMARY KEY,
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    cast_name VARCHAR(255) NOT NULL,
    role VARCHAR(100)
);

CREATE TABLE ratings (
    rating_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    rating NUMERIC(2,1) NOT NULL CHECK (rating >= 1.0 AND rating <= 5.0),
    review TEXT,
    tag TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    is_quarantined BOOLEAN DEFAULT FALSE
);

CREATE TABLE fraud_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    rating_id INTEGER REFERENCES ratings(rating_id),
    movie_id INTEGER REFERENCES movies(movie_id),
    severity VARCHAR(20),
    trigger VARCHAR(100),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE badges (
    badge_id SERIAL PRIMARY KEY,
    title VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    milestone INTEGER NOT NULL
);

CREATE TABLE user_badges (
    badge_id INTEGER NOT NULL REFERENCES badges(badge_id),
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    awarded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (badge_id, user_id)
);

CREATE TABLE watchlists (
    watchlist_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE watchlist_movies (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(watchlist_id),
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    added_at TIMESTAMP NOT NULL,
    PRIMARY KEY (watchlist_id, movie_id)
);

CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id),
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP
);

CREATE TABLE user_preferences (
    preference_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id),
    preference_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE user_reference_movies (
    reference_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    movie_id INTEGER NOT NULL REFERENCES movies(movie_id),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE genre_families (
    family_id SERIAL PRIMARY KEY,
    family_name VARCHAR(255) NOT NULL
);

CREATE TABLE genre_family_members (
    family_id INTEGER NOT NULL REFERENCES genre_families(family_id),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (family_id, genre_id)
);

CREATE TABLE topics (
    topic_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE review_sentiment (
    sentiment_id SERIAL PRIMARY KEY,
    rating_id INTEGER NOT NULL REFERENCES ratings(rating_id),
    sentiment_label VARCHAR(20) NOT NULL,
    sentiment_score NUMERIC(4,3),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE rating_topics (
    rating_topic_id SERIAL PRIMARY KEY,
    rating_id INTEGER NOT NULL REFERENCES ratings(rating_id),
    topic_id INTEGER NOT NULL REFERENCES topics(topic_id),
    relevance_score NUMERIC(4,3)
);

CREATE OR REPLACE FUNCTION calculate_movie_avg_rating()
RETURNS TRIGGER AS $$
BEGIN
    -- Handle INSERT and UPDATE (the new/current state of the rating)
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') THEN
        UPDATE movies 
        SET avg_rating = (
            SELECT ROUND(AVG(rating), 2) -- Ensures it fits numeric(3,2)
            FROM ratings 
            WHERE movie_id = NEW.movie_id
        )
        WHERE movie_id = NEW.movie_id;
    END IF;

    -- Handle DELETE or if the movie_id was CHANGED (the old state)
    IF (TG_OP = 'DELETE' OR (TG_OP = 'UPDATE' AND OLD.movie_id IS DISTINCT FROM NEW.movie_id)) THEN
        UPDATE movies 
        SET avg_rating = (
            SELECT ROUND(AVG(rating), 2) 
            FROM ratings 
            WHERE movie_id = OLD.movie_id
        )
        WHERE movie_id = OLD.movie_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;