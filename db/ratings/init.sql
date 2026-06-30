DROP TABLE IF EXISTS rating_topics CASCADE;
DROP TABLE IF EXISTS review_sentiment CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS fraud_alerts CASCADE;
DROP TABLE IF EXISTS ratings CASCADE;


CREATE TABLE ratings (
    rating_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    movie_id INTEGER NOT NULL,
    rating NUMERIC(2,1) NOT NULL CHECK (rating >= 1.0 AND rating <= 5.0),
    review TEXT,
    tag TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    is_quarantined BOOLEAN DEFAULT FALSE
);

CREATE TABLE fraud_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    rating_id INTEGER REFERENCES ratings(rating_id),
    movie_id INTEGER,
    severity VARCHAR(20),
    trigger VARCHAR(100),
    created_at TIMESTAMP NOT NULL
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

CREATE INDEX idx_ratings_movie_id ON ratings(movie_id);
CREATE INDEX idx_ratings_user_id ON ratings(user_id);
CREATE INDEX idx_ratings_is_quarantined ON ratings(is_quarantined);