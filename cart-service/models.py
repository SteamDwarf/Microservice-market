from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class CartItemBase(SQLModel):
    product_id: int = Field(index=True)
    quantity: int = Field(default=1, gt=0)


class CartItem(CartItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_id: int = Field(foreign_key="cart.id")

    cart: "Cart" = Relationship(back_populates="items")


class CartItemRead(CartItemBase):
    id: int


class CartItemPatch(SQLModel):
    quantity: int


class CartBase(SQLModel):
    user_id: int = Field(unique=True, index=True)


class Cart(CartBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    items: List[CartItem] = Relationship(back_populates="cart")


class CartRead(CartBase):
    id: int
    items: List[CartItemRead]
