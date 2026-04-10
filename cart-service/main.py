from contextlib import asynccontextmanager

from config import settings
from database import get_session, init_db
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from model import Cart, CartItem, CartItemBase, CartItemPatch, CartRead
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from utils import get_current_user_id, get_product


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
    user_id: int = Depends(get_current_user_id),
):
    cart = await get_or_create_cart(session, user_id)

    return cart


@cart_router.post("/items/", response_model=CartRead)
async def add_items(
    cart_item: CartItemBase,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
):
    product = await get_product(cart_item.product_id)

    if product.quantity < cart_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {product.quantity}",
        )

    cart = await get_or_create_cart(session, user_id)

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

    return await get_or_create_cart(session, user_id)


@cart_router.patch("/items/{id}/", response_model=CartRead)
async def increase_quantity(
    id: int,
    patch_data: CartItemPatch,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
):
    cart = await get_or_create_cart(session, user_id)
    existing_item = await get_cart_item(session, cart, id)

    await change_cart_item_quantity(
        session, existing_item, patch_data.quantity
    )

    await session.commit()
    await session.refresh(cart)

    return await get_or_create_cart(session, user_id)


@cart_router.delete("/items/{id}/", response_model=CartRead)
async def delete_cart_item(
    id: int,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
):
    cart = await get_or_create_cart(session, user_id)
    existing_item = await get_cart_item(session, cart, id)

    await session.delete(existing_item)
    await session.commit()
    await session.refresh(cart)

    return await get_or_create_cart(session, user_id)


app.include_router(cart_router)
