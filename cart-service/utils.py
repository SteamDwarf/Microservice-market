import httpx
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from common.model import ProductRead

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="http://auth-service:8000/api/auth/token/"
)


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "http://auth-service:8000/api/auth/profile/",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid token")

            user_data = response.json()

            return user_data["id"]
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
