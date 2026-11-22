from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.schemas.coupon_schemas import CouponCreate, CouponResponse, CouponUpdate, CouponValidateResponse
from app.services import coupon_service

router = APIRouter()


@router.get("", dependencies=[Depends(get_current_admin)], response_model=list[CouponResponse])
def list_coupons(db: Session = Depends(get_db)):
    """Lista todos los cupones creados para administración."""
    return coupon_service.list_coupons(db)


@router.post("", dependencies=[Depends(get_current_admin)], response_model=CouponResponse, status_code=status.HTTP_201_CREATED)
def create_coupon(data: CouponCreate, db: Session = Depends(get_db)):
    """Crea un nuevo cupón de descuento porcentual para la web."""
    return coupon_service.create_coupon(db, data)


@router.put("/{coupon_id}", dependencies=[Depends(get_current_admin)], response_model=CouponResponse)
@router.patch("/{coupon_id}", dependencies=[Depends(get_current_admin)], response_model=CouponResponse)
def update_coupon(coupon_id: int, data: CouponUpdate, db: Session = Depends(get_db)):
    """Actualiza un cupón existente (cambiar porcentaje o pausar/activar)."""
    return coupon_service.update_coupon(db, coupon_id, data)


@router.delete("/{coupon_id}", dependencies=[Depends(get_current_admin)], status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    """Elimina definitivamente un cupón."""
    coupon_service.delete_coupon(db, coupon_id)


@router.get("/validate/{code}", response_model=CouponValidateResponse)
def validate_web_coupon(code: str, db: Session = Depends(get_db)):
    """Valida un código de cupón para pedidos web sin requerir autenticación de administrador."""
    return coupon_service.validate_web_coupon(db, code)
