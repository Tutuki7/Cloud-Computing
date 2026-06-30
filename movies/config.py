from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, Text, Numeric
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "postgres-movies")
DB_NAME     = os.getenv("DB_NAME", "movies_db")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_URL      = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

KEYCLOAK_URL    = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM  = os.getenv("KEYCLOAK_REALM", "cc2526")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class MovieTable(Base):
    __tablename__ = "movies"

    movie_id = Column(Integer, primary_key=True, autoincrement=True)
    movie_title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    imdb_url = Column(Text, nullable=True)
    release_year = Column(Integer, nullable=False)
    runtime = Column(Integer, nullable=True)
    parental_rating = Column(String(20), nullable=True)
    poster_url = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False)
    avg_rating = Column(Numeric(3, 2), nullable=True)

class GenreTable(Base):
    __tablename__ = "genres"

    genre_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)

class MovieGenreTable(Base):
    __tablename__ = "movie_genres"

    movie_id = Column(Integer, ForeignKey("movies.movie_id"), primary_key=True)
    genre_id = Column(Integer, ForeignKey("genres.genre_id"), primary_key=True)

class MovieCastTable(Base):
    __tablename__ = "movie_cast"

    cast_id = Column(Integer, primary_key=True, autoincrement=True)
    movie_id = Column(Integer, ForeignKey("movies.movie_id"), nullable=False)
    cast_name = Column(String(255), nullable=False)
    role = Column(String(100), nullable=True)
