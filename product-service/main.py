from contextlib import asynccontextmanager

from config import settings
from database import get_session, init_db
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from models import Product
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from common.model import ProductRead


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
