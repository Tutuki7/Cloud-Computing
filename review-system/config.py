from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, ForeignKey,Integer, String, DateTime,  Boolean, Float, Text
from users.users_client import UserGrpcClient
from movies.movies_client import MovieGrpcClient
from datetime import datetime
from dotenv import load_dotenv
from google.cloud import pubsub_v1
import os
import json

load_dotenv()

DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

USERS_GRPC_URL = os.getenv("USER_GRPC_URL")
MOVIES_GRPC_URL = os.getenv("MOVIE_GRPC_URL")

PROJECT_ID = os.getenv("PROJECT_ID")
TOPIC_ID = os.getenv("PUBSUB_TOPIC", "review-created")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

user_client = UserGrpcClient(target=USERS_GRPC_URL)
movie_client = MovieGrpcClient(target=MOVIES_GRPC_URL)

publisher = None
topic_path = None

try:
    if PROJECT_ID:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
except Exception as e:
    print(f"CRITICAL WARNING: Failed to initialize Pub/Sub client: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def publish_review(rating_id: int, review_text: str):
    if not topic_path or not publisher:
        print('Pub/Sub configuration error')
        return
    data = json.dumps({"rating_id": rating_id, "review": review_text}).encode("utf-8")
    future = publisher.publish(topic_path, data)
    print(f"Published review: {future.result}")

class RatingTable(Base):
    __tablename__ = "ratings"

    rating_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    movie_id = Column(Integer, nullable=False)
    rating = Column(Float, nullable=False)
    review = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now())
    updated_at = Column(DateTime, default=datetime.now(), onupdate=datetime.now())
    is_quarantined = Column(Boolean, default=False) 
    tag = Column(Text, nullable=True)

class ReviewSentiment(Base):
    __tablename__ = "review_sentiment"
    sentiment_id = Column(Integer, primary_key=True)
    rating_id = Column(Integer, ForeignKey('ratings.rating_id'))
    sentiment_label = Column(String(20), nullable=False)
    sentiment_score = Column(Float)
    created_at = Column(DateTime, default=datetime.now())

class Topic(Base):
    __tablename__ = 'topics'
    topic_id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

class RatingTopic(Base):
    __tablename__ = 'rating_topics'
    rating_topic_id = Column(Integer, primary_key=True)
    rating_id = Column(Integer, ForeignKey('ratings.rating_id'))
    topic_id = Column(Integer, ForeignKey('topics.topic_id'))
    relevance_score = Column(Float)