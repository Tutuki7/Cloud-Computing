DROP TABLE IF EXISTS genre_family_members CASCADE;
DROP TABLE IF EXISTS genre_families CASCADE;
DROP TABLE IF EXISTS movie_cast CASCADE;
DROP TABLE IF EXISTS movie_genres CASCADE;
DROP TABLE IF EXISTS genres CASCADE;
DROP TABLE IF EXISTS movies CASCADE;

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

CREATE TABLE genre_families (
    family_id SERIAL PRIMARY KEY,
    family_name VARCHAR(255) NOT NULL
);

CREATE TABLE genre_family_members (
    family_id INTEGER NOT NULL REFERENCES genre_families(family_id),
    genre_id INTEGER NOT NULL REFERENCES genres(genre_id),
    PRIMARY KEY (family_id, genre_id)
);

