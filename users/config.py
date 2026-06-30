from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "postgres-users")
DB_NAME     = os.getenv("DB_NAME", "users_db")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_URL      = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Keycloak settings
KEYCLOAK_URL           = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM         = os.getenv("KEYCLOAK_REALM", "cc2526")
KEYCLOAK_CLIENT_ID     = os.getenv("KEYCLOAK_CLIENT_ID", "users-service")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")

engine = create_engine(DB_URL)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()

class UserTable(Base):
    __tablename__ = "users"

    user_id    = Column(Integer, primary_key=True, autoincrement=True)
    username   = Column(String(255), unique=True, nullable=False)
    email      = Column(String(255), unique=True, nullable=False)
    password   = Column(String(255), nullable=False)   # kept for DB compat; unused for auth
    gender     = Column(String(10), nullable=True)
    age        = Column(Integer, nullable=True)
    is_admin   = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class UserOAuthTable(Base):
    __tablename__ = "user_oauth"

    user_id       = Column(Integer, ForeignKey("users.user_id"), primary_key=True)
    provider      = Column(String(50), nullable=False)
    provider_id   = Column(String(255), nullable=False)
    refresh_token = Column(String(255), nullable=True)
    expires_at    = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.now)
    updated_at    = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# UserSessionTable kept for DB schema compatibility only
class UserSessionTable(Base):
    __tablename__ = "user_sessions"

    session_id    = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    refresh_token = Column(String(255), nullable=False)
    expires_at    = Column(DateTime, nullable=False)
    revoked       = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.now)
