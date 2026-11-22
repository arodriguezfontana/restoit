"""Servicio para la lógica comercial de cupones de descuento web."""

from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.db.session import transaction
from app.models.coupon import Coupon
from app.repositories import coupon_repository
from app.schemas.coupon_schemas import CouponCreate, CouponResponse, CouponUpdate, CouponValidateResponse


def list_coupons(db: Session) -> list[CouponResponse]:
    coupons = coupon_repository.list_all(db)
    return [CouponResponse.model_validate(c) for c in coupons]


def get_coupon(db: Session, coupon_id: int) -> Coupon:
    coupon = coupon_repository.get_by_id(db, coupon_id)
    if not coupon:
        raise NotFoundError("El cupón no existe.")
    return coupon


def create_coupon(db: Session, data: CouponCreate) -> CouponResponse:
    code = data.code.strip().upper()
    if coupon_repository.code_exists(db, code):
        raise ConflictError(f"Ya existe un cupón con el código '{code}'.")

    if data.discount_percentage < 1 or data.discount_percentage > 100:
        raise BusinessRuleError("El porcentaje de descuento debe estar entre 1% y 100%.")

    with transaction(db):
        coupon = Coupon(
            code=code,
            discount_percentage=data.discount_percentage,
            is_active=data.is_active,
        )
        coupon_repository.add(db, coupon)

    db.refresh(coupon)
    return CouponResponse.model_validate(coupon)


def update_coupon(db: Session, coupon_id: int, data: CouponUpdate) -> CouponResponse:
    coupon = get_coupon(db, coupon_id)

    with transaction(db):
        if data.code is not None:
            code = data.code.strip().upper()
            if coupon_repository.code_exists(db, code, exclude_id=coupon_id):
                raise ConflictError(f"Ya existe otro cupón con el código '{code}'.")
            coupon.code = code

        if data.discount_percentage is not None:
            if data.discount_percentage < 1 or data.discount_percentage > 100:
                raise BusinessRuleError("El porcentaje de descuento debe estar entre 1% y 100%.")
            coupon.discount_percentage = data.discount_percentage

        if data.is_active is not None:
            coupon.is_active = data.is_active

    db.refresh(coupon)
    return CouponResponse.model_validate(coupon)


def delete_coupon(db: Session, coupon_id: int) -> None:
    coupon = get_coupon(db, coupon_id)
    with transaction(db):
        coupon_repository.delete(db, coupon)


def validate_web_coupon(db: Session, code: str) -> CouponValidateResponse:
    cleaned = code.strip().upper()
    coupon = coupon_repository.get_by_code(db, cleaned)
    if not coupon:
        return CouponValidateResponse(
            valid=False,
            code=cleaned,
            discount_percentage=0,
            message="El cupón ingresado no existe.",
        )
    if not coupon.is_active:
        return CouponValidateResponse(
            valid=False,
            code=cleaned,
            discount_percentage=0,
            message="El cupón ingresado se encuentra inactivo o vencido.",
        )
    return CouponValidateResponse(
        valid=True,
        code=coupon.code,
        discount_percentage=coupon.discount_percentage,
        message=f"¡Cupón aplicado! Tenés un {coupon.discount_percentage}% de descuento.",
    )
