import httpx
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from common.models import CartRead, ProductRead, UserRead

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


""" async def init_broker(broker: RabbitBroker):
    connected = False

    for i in range(10):
        try:
            await broker.connect()
            connected = True
            break
        except (AMQPConnectionError, ConnectionError):
            print(f"RabbitMQ пока недоступен (попытка {i + 1})...")
            await asyncio.sleep(3)

    if not connected:
        raise RuntimeError(
            "Не удалось подключиться к RabbitMQ после 10 попыток"
        )
 """
