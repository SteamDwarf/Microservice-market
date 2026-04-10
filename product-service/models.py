from typing import Optional

from sqlmodel import Field

from common.model import ProductBase


class Product(ProductBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
