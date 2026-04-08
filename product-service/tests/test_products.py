from decimal import Decimal

from httpx import AsyncClient
from models import Product


class TestProductService:
    async def test_get_products_empty(self, client: AsyncClient):
        response = await client.get("/api/products/")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_and_get_products(self, client: AsyncClient, session):
        new_product = Product(
            name="Тестовый товар",
            description="Описание",
            cost_price=Decimal("100.00"),
            quantity=10,
        )

        session.add(new_product)
        await session.commit()

        response = await client.get("/api/products/")
        assert response.status_code == 200

        data = response.json()

        assert len(data) == 1
        assert data[0]["name"] == "Тестовый товар"

        assert Decimal(str(data[0]["user_price"])) == Decimal("120.00")
