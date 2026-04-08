from decimal import Decimal
from typing import Optional

from sqlmodel import Field, SQLModel


class ProductBase(SQLModel):
    name: str = Field(index=True, unique=True, max_length=255)
    description: Optional[str] = Field(default=None)
    cost_price: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    quantity: int = Field(default=0, ge=0)

    @property
    def user_price(self) -> Decimal:
        return (self.cost_price * Decimal("1.2")).quantize(Decimal("0.01"))


class Product(ProductBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class ProductRead(ProductBase):
    id: int
    user_price: Decimal
