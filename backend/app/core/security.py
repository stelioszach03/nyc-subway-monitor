"""
Security utilities for authentication and authorization.
Currently placeholder - would implement JWT/OAuth in production.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()

# Security configuration
SECRET_KEY = "your-secret-key-here"  # In production, use environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security
security = HTTPBearer()


class TokenData(BaseModel):
    """JWT token payload."""
    username: Optional[str] = None
    scopes: list[str] = []


class User(BaseModel):
    """User model."""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    scopes: list[str] = []


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
            
        token_scopes = payload.get("scopes", [])
        token_data = TokenData(username=username, scopes=token_scopes)
        
    except JWTError:
        raise credentials_exception
    
    # In production, would fetch user from database
    user = User(
        username=token_data.username,
        scopes=token_data.scopes,
        disabled=False,
    )
    
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    return user


def check_permissions(required_scopes: list[str]):
    """Check if user has required permissions."""
    async def permission_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        """Verify user has required scopes."""
        if not required_scopes:
            return current_user
        
        token_scopes = set(current_user.scopes)
        required_scopes_set = set(required_scopes)
        
        if not required_scopes_set.issubset(token_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": 'Bearer scope="{}"'.format(
                    " ".join(required_scopes)
                )},
            )
        
        return current_user
    
    return permission_checker


# Rate limiting decorator
from functools import wraps
from collections import defaultdict
import time

rate_limit_storage = defaultdict(list)


def rate_limit(max_calls: int, time_window: int):
    """Simple in-memory rate limiting decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client identifier (would use IP or user ID in production)
            client_id = "default"  # Simplified
            
            now = time.time()
            calls = rate_limit_storage[client_id]
            
            # Remove old calls outside time window
            calls = [call_time for call_time in calls if now - call_time < time_window]
            rate_limit_storage[client_id] = calls
            
            if len(calls) >= max_calls:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {max_calls} calls per {time_window} seconds",
                )
            
            # Record this call
            rate_limit_storage[client_id].append(now)
            
            # Execute function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# API key validation (simplified)
API_KEYS = {
    "demo-api-key": {
        "name": "Demo Application",
        "scopes": ["read", "write"],
    }
}


async def get_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """Validate API key."""
    api_key = credentials.credentials
    
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return API_KEYS[api_key]