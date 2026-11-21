from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CouponCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Código de cupón único")
    discount_percentage: int = Field(..., ge=1, le=100, description="Porcentaje de descuento (1 a 100)")
    is_active: bool = Field(default=True, description="Si el cupón está activo para pedidos web")


class CouponUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    discount_percentage: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class CouponResponse(BaseModel):
    id: int
    code: str
    discount_percentage: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CouponValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_percentage: int
    message: str | None = None
