"""
Authentication Routes
=====================
FastAPI endpoints for user registration, login, and authentication.

Endpoints:
  POST /auth/register  → Register a new user
  POST /auth/login     → Login and receive JWT token
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.auth_schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new user account.
    
    Args:
        user_data: Registration data (email, first_name, last_name, password, confirm_password)
        db: Database session
        
    Returns:
        TokenResponse with access token and user info
        
    Raises:
        HTTPException 400: If registration fails (passwords don't match, email exists, etc.)
    """
    try:
        # Register user
        user = auth_service.register_user(db, user_data)
        
        # Generate token
        token = auth_service.create_access_token(user.id, user.email)
        
        # Return response
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """
    Login with email and password.
    
    Args:
        login_data: Login credentials (email, password)
        db: Database session
        
    Returns:
        TokenResponse with access token and user info
        
    Raises:
        HTTPException 401: If credentials are invalid
    """
    try:
        # Authenticate user
        user = auth_service.login_user(db, login_data)
        
        # Generate token
        token = auth_service.create_access_token(user.id, user.email)
        
        # Return response
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )
