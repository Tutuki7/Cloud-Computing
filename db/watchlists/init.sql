DROP TABLE IF EXISTS watchlist_movies CASCADE;
DROP TABLE IF EXISTS watchlists CASCADE;

CREATE TABLE watchlists (
    watchlist_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE watchlist_movies (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(watchlist_id),
    movie_id INTEGER NOT NULL,
    added_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (watchlist_id, movie_id)
);

