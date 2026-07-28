from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.models.user import User
from app.services.auth_service import InvalidCredentialsError


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def get_current_user(request: Request) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    try:
        authenticated = await request.app.state.auth_service.authenticate(token)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required") from exc

    if request.method not in SAFE_METHODS:
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
        csrf_header = request.headers.get("X-CSRF-Token")
        if not request.app.state.auth_service.verify_csrf(authenticated.session, csrf_cookie, csrf_header):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
        origin = request.headers.get("Origin")
        if origin and not _allowed_origin(origin, request):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")

    request.state.auth_session = authenticated.session
    return authenticated.user


def _allowed_origin(origin: str, request: Request) -> bool:
    settings = get_settings()
    allowed = set(settings.cors_origin_list)
    request_origin = f"{request.url.scheme}://{request.url.netloc}"
    parsed = urlparse(origin)
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    return normalized == request_origin or normalized in allowed
