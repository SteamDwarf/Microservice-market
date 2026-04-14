from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from sqlmodel import Column, DateTime, Field, Relationship, SQLModel, func


class OrderStatus(str, Enum):
    PENDING = "Ожидает"
    PAID = "Оплачен"
    CANCELLED = "Отменён"


class OrderItemBase(SQLModel):
    product_id: int
    quantity: int = Field(gt=0)


class OrderItemRead(OrderItemBase):
    id: int
    price_paid: Decimal


class OrderBase(SQLModel):
    status: OrderStatus = OrderStatus.PENDING


class OrderRead(OrderBase):
    id: int
    user_id: int
    total: Decimal
    created_at: datetime
    items: List[OrderItemRead]


class OrderItem(OrderItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(
        foreign_key="order.id", index=True, ondelete="CASCADE"
    )
    price_paid: Decimal = Field(max_digits=12, decimal_places=2)

    order: "Order" = Relationship(back_populates="items")


class Order(OrderBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    total: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )
    )

    items: List[OrderItem] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
