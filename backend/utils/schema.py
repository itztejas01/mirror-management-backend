from pydantic import BaseModel
from typing import List, Optional


class UserLoginSchema(BaseModel):
    email: str
    password: str


class UserSchema(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str
    updated_at: str


class SizeSheetItem(BaseModel):
    # Optional customer provided identifier for the line item
    customer_order_no: Optional[str] = ""
    # Product/description fields
    product_name: Optional[str] = ""
    thickness: Optional[str] = ""
    # Dimensions
    size_width: float
    size_height: float
    # Optional fractional inch strings when unit == "inch" (e.g., "1/2")
    size_width_fraction: Optional[str] = ""
    size_height_fraction: Optional[str] = ""
    width_rounding_value: Optional[int] = 0
    height_rounding_value: Optional[int] = 0
    # Unit: one of ["ft", "inch", "mm"]
    unit: str = "ft"
    # Quantity
    quantity: int = 1
    # Optional weight and rate fields for display
    weight: Optional[float] = 0
    note: Optional[str] = ""


class SizeSheetRequest(BaseModel):
    items: List[SizeSheetItem]
    # Optional title for the sheet; defaults to "Size Sheet"
    title: Optional[str] = "Size Sheet"
    # Optional remarks to print at the bottom
    remarks: Optional[str] = ""
