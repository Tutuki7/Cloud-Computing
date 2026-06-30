from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from ratings.rating_client import ReviewGrpcClient
from users.users_client import UserGrpcClient
from movies.movies_client import MovieGrpcClient
from datetime import datetime
from dotenv import load_dotenv
from google import genai
import os

load_dotenv()
DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
REVIEW_GRPC_URL = os.getenv("REVIEW_GRPC_URL")
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION", "europe-west1")
MODEL = os.getenv("MODEL", "gemini-2.5-flash")
USERS_GRPC_URL = os.getenv("USER_GRPC_URL")
MOVIES_GRPC_URL = os.getenv("MOVIE_GRPC_URL")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

review_client = ReviewGrpcClient(target=REVIEW_GRPC_URL)
user_client = UserGrpcClient(target=USERS_GRPC_URL)
movie_client = MovieGrpcClient(target=MOVIES_GRPC_URL)

vertex_client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserPreferenceTable(Base):
    __tablename__ = "user_preferences"
    preference_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    genre_id = Column(Integer, nullable=False)
    preference_type = Column(String(10), nullable=False, default="like")
    created_at = Column(DateTime, default=datetime.now())

class UserReferenceMovieTable(Base):
    __tablename__ = "user_reference_movies"
    reference_id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now())