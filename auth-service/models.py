from decimal import Decimal
from typing import Optional

from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)


class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    balance: Decimal = Field(default=0, max_digits=12, decimal_places=2)


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserLogin(SQLModel):
    username: str
    password: str


class UserRead(UserBase):
    id: int
    balance: Decimal


class TopUp(SQLModel):
    amount: Decimal = Field(gt=0)


class AccessToken(SQLModel):
    access: str
    token_type: str


class TokenPair(AccessToken):
    refresh: str
