from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from dotenv import load_dotenv
from users.users_client import UserGrpcClient
import os

load_dotenv()
DB_URL = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
USERS_GRPC_URL = os.getenv("USER_GRPC_URL")

engine = create_engine(DB_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

user_client = UserGrpcClient(target=USERS_GRPC_URL)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class SubscriptionTable(Base):
    __tablename__ = "subscriptions"

    subscription_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True)
    type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
