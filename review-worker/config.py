from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, ForeignKey,Integer, String, DateTime,  Boolean, Float, Text
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime
from dotenv import load_dotenv
from google.cloud import pubsub_v1
from google import genai
import os

load_dotenv()

DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION", "europe-west1")
SUB_ID = os.getenv("PUBSUB_SUBSCRIPTION")
MODEL = os.getenv("MODEL", "gemini-2.5-flash")

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

vertexai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(PROJECT_ID, SUB_ID)

class RatingTable(Base):
    __tablename__ = "ratings"

    rating_id = Column(Integer, primary_key=True, index=True)

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
