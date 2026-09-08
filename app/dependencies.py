from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole
from app.utils import decode_token

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, settings.jwt_secret_key, "access")
        email = payload.get("sub")
    except ValueError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise credentials_exception
    if int(payload.get("ver", 0)) != int(user.auth_version or 1):
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return user


def require_role(*roles: UserRole):
    def guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
        return current_user
    return guard


require_student = require_role(UserRole.student)
require_recruiter = require_role(UserRole.recruiter)
require_institution_admin = require_role(UserRole.institution_admin, UserRole.platform_admin)
require_platform_admin = require_role(UserRole.platform_admin)
