import asyncio
from decimal import Decimal

from database import engine, init_db
from models import Product
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def seed_products():
    # Список товаров для добавления
    await init_db()

    initial_products = [
        Product(
            name="Кофеварка",
            description="Варит отличный эспрессо",
            cost_price=Decimal("5000.00"),
            quantity=10,
        ),
        Product(
            name="Чайник",
            description="Быстро закипает",
            cost_price=Decimal("1500.00"),
            quantity=25,
        ),
        Product(
            name="Тостер",
            description="Два режима обжарки",
            cost_price=Decimal("2000.00"),
            quantity=15,
        ),
    ]

    # Открываем сессию вручную
    async with AsyncSession(engine) as session:
        for product in initial_products:
            statement = select(Product).where(Product.name == product.name)
            result = await session.execute(statement)

            if not result.scalars().first():
                session.add(product)
                print(f"Добавляю: {product.name}")

        await session.commit()
        print("База успешно наполнена!")


if __name__ == "__main__":
    asyncio.run(seed_products())
