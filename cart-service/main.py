from contextlib import asynccontextmanager

from config import settings
from database import get_session, init_db, session_context
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from models import Cart, CartItem, CartItemBase, CartItemPatch, CartRead
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import delete, select

from common.models import UserRead
from common.utils import (
    connect_broker_with_retry,
    get_current_user,
    get_product,
    get_rabbitmq_url,
)

# ... твои импорты сессии ...

broker = RabbitBroker(get_rabbitmq_url())
app_stream = FastStream(broker)


@broker.subscriber("cart.clear")
async def handle_cart_clear(data: dict):
    user_id = data.get("user_id")

    async with session_context() as session:
        # 1. Находим ID корзины пользователя
        cart_stmt = select(Cart.id).where(Cart.user_id == user_id)
        cart_id = (await session.execute(cart_stmt)).scalar_one_or_none()

        if cart_id:
            # 2. Удаляем все товары из этой корзины
            delete_stmt = delete(CartItem).where(CartItem.cart_id == cart_id)
            await session.execute(delete_stmt)
            await session.commit()
            print(f"Корзина пользователя {user_id} успешно очищена.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await connect_broker_with_retry(broker)

    yield

    await broker.stop()


app = FastAPI(lifespan=lifespan)
cart_router = APIRouter(prefix="/api/cart", tags=["Cart"])


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


async def get_or_create_cart(session: AsyncSession, user_id: int) -> Cart:
    statement = (
        select(Cart)
        .where(Cart.user_id == user_id)
        .options(selectinload(Cart.items))
    )
    result = await session.execute(statement)
    cart = result.scalar_one_or_none()

    if not cart:
        cart = Cart(user_id=user_id, items=[])
        session.add(cart)

        await session.flush()

    return cart


async def change_cart_item_quantity(
    session: AsyncSession, cart_item: CartItem, quantity: int
):
    product = await get_product(cart_item.product_id)

    cart_item.quantity += quantity

    if cart_item.quantity > product.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {product.quantity}",
        )

    session.add(cart_item)


async def get_cart_item(
    session: AsyncSession, cart: Cart, item_id: int, strict: bool = True
) -> CartItem:
    statement = select(CartItem).where(
        CartItem.cart_id == cart.id,
        CartItem.id == item_id,
    )

    result = await session.execute(statement)
    cart_item = result.scalars().first()

    if not cart_item and strict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item with id {item_id} not found in user cart",
        )

    return cart_item


@cart_router.get("/", response_model=CartRead)
async def cart(
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
):
    cart = await get_or_create_cart(session, user.id)

    return cart


@cart_router.post("/items/", response_model=CartRead)
async def add_items(
    cart_item: CartItemBase,
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
):
    product = await get_product(cart_item.product_id)

    if product.quantity < cart_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {product.quantity}",
        )

    cart = await get_or_create_cart(session, user.id)

    statement = select(CartItem).where(
        CartItem.cart_id == cart.id,
        CartItem.product_id == cart_item.product_id,
    )

    result = await session.execute(statement)
    existing_item = result.scalars().first()

    if existing_item:
        await change_cart_item_quantity(
            session, existing_item, cart_item.quantity
        )
    else:
        new_item = CartItem(
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            cart_id=cart.id,
        )
        session.add(new_item)

    await session.commit()
    await session.refresh(cart)

    return await get_or_create_cart(session, user.id)


@cart_router.patch("/items/{id}/", response_model=CartRead)
async def increase_quantity(
    id: int,
    patch_data: CartItemPatch,
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
):
    cart = await get_or_create_cart(session, user.id)
    existing_item = await get_cart_item(session, cart, id)

    await change_cart_item_quantity(
        session, existing_item, patch_data.quantity
    )

    await session.commit()
    await session.refresh(cart)

    return await get_or_create_cart(session, user.id)


@cart_router.delete("/items/{id}/", response_model=CartRead)
async def delete_cart_item(
    id: int,
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
):
    cart = await get_or_create_cart(session, user.id)
    existing_item = await get_cart_item(session, cart, id)

    await session.delete(existing_item)
    await session.commit()
    await session.refresh(cart)

    return await get_or_create_cart(session, user.id)


app.include_router(cart_router)
