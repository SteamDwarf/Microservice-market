from contextlib import asynccontextmanager

from config import settings
from database import get_session, init_db, session_context
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from models import Product, ProductRead
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from common.utils import connect_broker_with_retry, get_rabbitmq_url

broker = RabbitBroker(get_rabbitmq_url())
app_stream = FastStream(broker)


@broker.subscriber("stock.decrease")
async def handle_stock_decrease(data: dict):
    order_id = data.get("order_id")
    items = data.get("items", [])

    async with session_context() as session:
        for item_data in items:
            product_id = item_data["product_id"]
            qty_to_decrease = item_data["quantity"]

            statement = (
                select(Product)
                .where(Product.id == product_id)
                .with_for_update()
            )
            result = await session.execute(statement)
            product = result.scalar_one_or_none()

            if product:
                product.quantity -= qty_to_decrease
                session.add(product)
                print(
                    f"Deducted {qty_to_decrease} units of product "
                    f"{product.name} for order {order_id}"
                )
            else:
                print(
                    f"Error: Product {product_id} not found while "
                    f"deducting stock"
                )

        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await connect_broker_with_retry(broker)

    yield

    await broker.stop()


app = FastAPI(lifespan=lifespan)
products_router = APIRouter(prefix="/api", tags=["Products"])


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


@products_router.get("/products/", response_model=list[ProductRead])
async def products(session: AsyncSession = Depends(get_session)):
    statement = select(Product)
    result = await session.execute(statement)
    products_list = result.scalars().all()

    return products_list


@products_router.get("/products/{product_id}", response_model=ProductRead)
async def product_by_id(
    product_id: int, session: AsyncSession = Depends(get_session)
):
    product = await session.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found",
        )

    return product


app.include_router(products_router)
