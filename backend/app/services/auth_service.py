import asyncio
import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User
from app.models.user_session import UserSession
from app.models.conversation import Conversation


class InvalidCredentialsError(Exception):
    pass


class UsernameTakenError(Exception):
    pass


@dataclass(frozen=True)
class CreatedSession:
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: UserSession


def normalize_username(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        session_ttl_hours: int,
    ) -> None:
        self.session_factory = session_factory
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.password_hash = PasswordHash.recommended()
        self._dummy_password_hash = self.password_hash.hash(secrets.token_urlsafe(32))

    async def register(self, username: str, password: str) -> User:
        clean_username = unicodedata.normalize("NFKC", username).strip()
        normalized = normalize_username(clean_username)
        if len(normalized) < 3:
            raise ValueError("Username must contain at least 3 characters")
        password_hash = await asyncio.to_thread(self.password_hash.hash, password)
        user = User(
            username=clean_username,
            normalized_username=normalized,
            display_name=clean_username,
            password_hash=password_hash,
        )
        try:
            async with self.session_factory() as session:
                session.add(user)
                await session.flush()
                session.add(Conversation(user_id=user.id, title="新对话"))
                await session.commit()
                await session.refresh(user)
        except IntegrityError as exc:
            raise UsernameTakenError from exc
        return user

    async def login(self, username: str, password: str, user_agent: str | None) -> tuple[User, CreatedSession]:
        normalized = normalize_username(username)
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                select(User).where(User.normalized_username == normalized)
            )
            user = result.scalar_one_or_none()
            if user is None:
                await self._dummy_verify(password)
                raise InvalidCredentialsError
            if user.status != "active" or (user.locked_until and user.locked_until > now):
                raise InvalidCredentialsError
            valid = await asyncio.to_thread(self.password_hash.verify, password, user.password_hash)
            if not valid:
                user.failed_login_count += 1
                if user.failed_login_count >= 5:
                    user.locked_until = now + timedelta(minutes=15)
                    user.failed_login_count = 0
                await session.commit()
                raise InvalidCredentialsError

            user.failed_login_count = 0
            user.locked_until = None
            created = self._new_session(now)
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=token_hash(created.token),
                    csrf_hash=token_hash(created.csrf_token),
                    user_agent=(user_agent or "")[:512] or None,
                    expires_at=created.expires_at,
                )
            )
            await session.commit()
            return user, created

    async def authenticate(self, token: str | None) -> AuthenticatedSession:
        if not token:
            raise InvalidCredentialsError
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(
                    UserSession.token_hash == token_hash(token),
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                    User.status == "active",
                )
            )
            row = result.one_or_none()
            if row is None:
                raise InvalidCredentialsError
            auth_session, user = row
            auth_session.last_seen_at = now
            await session.commit()
            return AuthenticatedSession(user=user, session=auth_session)

    async def revoke(self, token: str | None) -> None:
        if not token:
            return
        async with self.session_factory() as session:
            await session.execute(
                update(UserSession)
                .where(UserSession.token_hash == token_hash(token), UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def revoke_all(self, user_id) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await session.commit()

    def verify_csrf(self, auth_session: UserSession, cookie_value: str | None, header_value: str | None) -> bool:
        if not cookie_value or not header_value:
            return False
        if not secrets.compare_digest(cookie_value, header_value):
            return False
        return secrets.compare_digest(token_hash(header_value), auth_session.csrf_hash)

    async def _dummy_verify(self, password: str) -> None:
        try:
            await asyncio.to_thread(self.password_hash.verify, password, self._dummy_password_hash)
        except Exception:
            pass

    def _new_session(self, now: datetime) -> CreatedSession:
        return CreatedSession(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=now + self.session_ttl,
        )
