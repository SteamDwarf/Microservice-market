from contextlib import asynccontextmanager
from decimal import Decimal

from auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from config import settings
from database import get_session, init_db, session_context
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from models import (
    AccessToken,
    TokenPair,
    TopUp,
    User,
    UserCreate,
    UserLogin,
    UserRead,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from common.utils import connect_broker_with_retry, get_rabbitmq_url

broker = RabbitBroker(get_rabbitmq_url())
app_stream = FastStream(broker)


@broker.subscriber("orders.created")
async def handle_order_payment(data: dict):
    user_id = data.get("user_id")
    order_id = data.get("order_id")
    total = Decimal(data.get("total"))

    async with session_context() as session:
        statement = select(User).where(User.id == user_id).with_for_update()
        result = await session.execute(statement)
        user = result.scalars().first()

        if user and user.balance >= total:
            user.balance -= total
            session.add(user)

            await session.commit()

            await broker.publish(
                {"order_id": order_id, "status": "success"},
                queue="payment.results",
            )

            print(
                f"Successfully charged {total} from user {user_id} "
                f"for order #{order_id}"
            )
        else:
            if not user:
                print(f"Error: User {user_id} not found")

            if user and user.balance < total:
                print(
                    f"Error: Insufficient funds for user {user_id} "
                    f"to pay for order {order_id}"
                )

            await broker.publish(
                {
                    "order_id": order_id,
                    "status": "fail",
                },
                queue="payment.results",
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await connect_broker_with_retry(broker)

    yield

    await broker.stop()


app = FastAPI(lifespan=lifespan)
auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])


if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@auth_router.post("/register/", response_model=UserRead)
async def register(
    user_in: UserCreate, session: AsyncSession = Depends(get_session)
):
    statement = select(User).where(User.username == user_in.username)
    result = await session.execute(statement)

    if result.first():
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
    )

    session.add(new_user)

    await session.commit()
    await session.refresh(new_user)

    return new_user


@auth_router.post("/token/", response_model=TokenPair)
async def login(
    login_data: UserLogin, session: AsyncSession = Depends(get_session)
):
    statement = select(User).where(User.username == login_data.username)
    result = await session.execute(statement)
    user = result.scalars().first()

    if not user or not verify_password(
        login_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Генерируем JWT
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    return {
        "access": access_token,
        "refresh": refresh_token,
        "token_type": "bearer",
    }


@auth_router.post("/token/refresh/", response_model=AccessToken)
async def refresh_access_token(
    refresh: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_session),
):
    try:
        # 1. Декодируем и проверяем токен
        payload = decode_token(refresh)

        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        username: str = payload.get("sub")

        if not username:
            raise HTTPException(
                status_code=401, detail="Invalid token payload"
            )

        statement = select(User).where(User.username == username)
        result = await session.execute(statement)
        user = result.scalars().first()

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        new_access_token = create_access_token(data={"sub": user.username})

        return {"access": new_access_token, "token_type": "bearer"}

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@auth_router.get("/profile/", response_model=UserRead)
async def profile(current_user: User = Depends(get_current_user)):
    print("PROFILE")
    return current_user


@auth_router.post("/topup/", response_model=UserRead)
async def top_up(
    payload: TopUp,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        statement = (
            update(User)
            .where(User.id == current_user.id)
            .values(balance=User.balance + payload.amount)
        )
        await session.execute(statement)
        await session.commit()
        await session.refresh(current_user)

        return current_user
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to top up balance"
        )


app.include_router(auth_router)
