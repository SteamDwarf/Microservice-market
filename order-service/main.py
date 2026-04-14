from contextlib import asynccontextmanager
from decimal import Decimal
from typing import List

from config import settings
from database import get_session, init_db, session_context
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from models import Order, OrderItem, OrderRead, OrderStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from common.models import UserRead
from common.utils import (
    connect_broker_with_retry,
    get_cart,
    get_current_user,
    get_product,
    get_rabbitmq_url,
)

# 1. Создаем брокер
broker = RabbitBroker(get_rabbitmq_url())
app_stream = FastStream(broker)


# В файле воркера OrderService
@broker.subscriber("payment.results")
async def handle_payment_result(data: dict):
    order_id = data.get("order_id")
    status = data.get("status")

    async with session_context() as session:
        statement = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items))
        )
        result = await session.execute(statement)
        order = result.scalar_one_or_none()

        if not order:
            return

        if status == "success":
            order.status = OrderStatus.PAID

            items_data = [
                {"product_id": item.product_id, "quantity": item.quantity}
                for item in order.items
            ]

            await broker.publish(
                {"order_id": order_id, "items": items_data},
                queue="stock.decrease",
            )

            await broker.publish(
                {"user_id": order.user_id}, queue="cart.clear"
            )

            print(f"Order {order_id} successfully paid")
        else:
            order.status = OrderStatus.CANCELLED
            print(f"Order {order_id} cancelled")

        session.add(order)
        await session.commit()


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="http://auth-service:8000/api/auth/token/"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await connect_broker_with_retry(broker)

    yield

    await broker.stop()


app = FastAPI(lifespan=lifespan)
orders_router = APIRouter(prefix="/api/orders", tags=["Orders"])


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


@orders_router.get("/", response_model=List[OrderRead])
async def list_orders(
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
):
    statement = (
        select(Order)
        .where(Order.user_id == user.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    results = await session.execute(statement)

    return results.scalars().all()


@orders_router.post("/", response_model=OrderRead)
async def create_order(
    session: AsyncSession = Depends(get_session),
    user: UserRead = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    cart = await get_cart(token)

    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty.")

    async with session.begin():
        total = Decimal("0")
        items_to_create = []

        for item in cart.items:
            product = await get_product(item.product_id)

            current_price = product.user_price
            item_total = current_price * item.quantity
            total += item_total

            items_to_create.append(
                OrderItem(
                    product_id=product.id,
                    quantity=item.quantity,
                    price_paid=current_price,
                )
            )

        if user.balance < total:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Required: {total}, on balance: {user.balance}",
            )

        new_order = Order(user_id=user.id, total=total)
        session.add(new_order)
        await session.flush()

        for order_item in items_to_create:
            order_item.order_id = new_order.id
            session.add(order_item)

        # 6. Финализация: списываем деньги и чистим корзину
    # Publish only after the order transaction is committed.
    await broker.publish(
        {
            "order_id": new_order.id,
            "user_id": user.id,
            "total": str(total),
        },
        queue="orders.created",
    )
    # Сбрасываем кэш объекта, чтобы подтянулись items для response_model
    statement = (
        select(Order)
        .where(Order.id == new_order.id)
        .options(selectinload(Order.items))
    )
    result = await session.execute(statement)

    return result.scalar_one()


app.include_router(orders_router)
