from decimal import Decimal
from typing import List

from sqlmodel import SQLModel


class UserRead(SQLModel):
    id: int
    balance: Decimal
    username: str
    email: str


class ProductRead(SQLModel):
    id: int
    name: str
    quantity: int
    user_price: Decimal


class CartItemRead(SQLModel):
    id: int
    product_id: int
    quantity: int


class CartRead(SQLModel):
    id: int
    user_id: int
    items: List[CartItemRead]
