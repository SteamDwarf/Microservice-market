import asyncio
import os

import httpx
from aiormq.exceptions import AMQPConnectionError
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from faststream.rabbit import RabbitBroker

from common.models import CartRead, ProductRead, UserRead

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="http://auth-service:8000/api/auth/token/"
)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRead:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "http://auth-service:8000/api/auth/profile/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid token")

            user_data = response.json()

            return UserRead(**user_data)
        except httpx.RequestError:
            raise HTTPException(
                status_code=503, detail="Auth service unavailable"
            )


async def get_product(product_id: int) -> ProductRead:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"http://product-service:8000/api/products/{product_id}"
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=404, detail="Product not found"
                )

            product_data = response.json()

            return ProductRead(**product_data)
        except httpx.RequestError as e:
            print(e)
            raise HTTPException(
                status_code=503, detail="Product service unavailable"
            )


async def get_cart(token: str) -> CartRead:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "http://cart-service:8000/api/cart/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=404, detail="Cart not found")

            cart_data = response.json()

            return CartRead(**cart_data)
        except httpx.RequestError as e:
            print(e)
            raise HTTPException(
                status_code=503, detail="Cart service unavailable"
            )


def get_rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)


async def connect_broker_with_retry(
    broker: RabbitBroker, retries: int = 10, delay: int = 3
) -> None:
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            # `connect()` only opens a connection. We need `start()` so
            # subscribers begin consuming messages from RabbitMQ.
            await broker.start()
            return
        except (AMQPConnectionError, ConnectionError, OSError) as exc:
            last_error = exc
            if attempt == retries:
                break

            print(
                f"RabbitMQ is unavailable "
                f"(attempt {attempt}/{retries}): {exc}"
            )
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"Could not connect to RabbitMQ after {retries} attempts"
    ) from last_error
