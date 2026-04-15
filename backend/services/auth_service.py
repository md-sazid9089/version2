"""
Authentication Service
======================
Business logic for user registration, login, password hashing, and JWT token generation.
"""

from datetime import datetime, timedelta
from typing import Optional
import bcrypt
import jwt
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from config import settings
from models.user_models import User
from models.auth_schemas import UserRegister, UserLogin, UserResponse


class AuthService:
    """Authentication service with password hashing and JWT handling."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), password_hash.encode('utf-8'))

    @staticmethod
    def create_access_token(user_id: int, user_email: str) -> str:
        """Create a JWT access token."""
        payload = {
            'sub': str(user_id),
            'email': user_email,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        }
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return token

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            return payload
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def register_user(db: Session, user_data: UserRegister) -> User:
        """
        Register a new user.
        
        Args:
            db: Database session
            user_data: User registration data
            
        Returns:
            Created User object
            
        Raises:
            ValueError: If passwords don't match or email already exists
        """
        # Validate passwords match
        if user_data.password != user_data.confirm_password:
            raise ValueError("Passwords do not match")

        # Check if email already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise ValueError(f"Email {user_data.email} is already registered")

        # Hash password
        password_hash = AuthService.hash_password(user_data.password)

        # Create new user
        new_user = User(
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password_hash=password_hash,
            is_active=True,
        )

        try:
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            return new_user
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Email {user_data.email} is already registered")

    @staticmethod
    def login_user(db: Session, login_data: UserLogin) -> User:
        """
        Authenticate a user and return user object.
        
        Args:
            db: Database session
            login_data: Login credentials
            
        Returns:
            Authenticated User object
            
        Raises:
            ValueError: If credentials are invalid
        """
        # Find user by email
        user = db.query(User).filter(User.email == login_data.email).first()
        if not user:
            raise ValueError("Invalid email or password")

        # Check if user is active
        if not user.is_active:
            raise ValueError("User account is inactive")

        # Verify password
        if not AuthService.verify_password(login_data.password, user.password_hash):
            raise ValueError("Invalid email or password")

        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        return db.query(User).filter(User.id == user_id).first()


# Singleton instance
auth_service = AuthService()
