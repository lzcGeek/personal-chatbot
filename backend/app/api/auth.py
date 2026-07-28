from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import get_settings
from app.models.user import User
from app.schemas.auth import AuthCredentials, AuthResponse, UserInfo
from app.services.auth_dependencies import get_current_user
from app.services.auth_service import InvalidCredentialsError, UsernameTakenError


router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def user_info(user: User) -> UserInfo:
    return UserInfo(id=user.id, username=user.username, display_name=user.display_name)


def set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: AuthCredentials, request: Request) -> AuthResponse:
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")
    try:
        user = await request.app.state.auth_service.register(payload.username, payload.password)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AuthResponse(user=user_info(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: AuthCredentials, request: Request, response: Response) -> AuthResponse:
    try:
        user, created = await request.app.state.auth_service.login(
            payload.username, payload.password, request.headers.get("User-Agent")
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password") from exc
    set_auth_cookies(response, created.token, created.csrf_token)
    return AuthResponse(user=user_info(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, _: User = Depends(get_current_user)) -> None:
    await request.app.state.auth_service.revoke(request.cookies.get(settings.session_cookie_name))
    clear_auth_cookies(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
) -> None:
    await request.app.state.auth_service.revoke_all(user.id)
    clear_auth_cookies(response)


@router.get("/me", response_model=AuthResponse)
async def me(user: User = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=user_info(user))
