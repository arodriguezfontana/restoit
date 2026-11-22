"""Repositorio para la gestión de cupones de descuento web."""

from sqlalchemy.orm import Session

from app.models.coupon import Coupon


def list_all(db: Session) -> list[Coupon]:
    return db.query(Coupon).order_by(Coupon.created_at.desc()).all()


def list_active(db: Session) -> list[Coupon]:
    return db.query(Coupon).filter(Coupon.is_active.is_(True)).order_by(Coupon.code.asc()).all()


def get_by_id(db: Session, coupon_id: int) -> Coupon | None:
    return db.query(Coupon).filter(Coupon.id == coupon_id).first()


def get_by_code(db: Session, code: str) -> Coupon | None:
    cleaned = code.strip().upper()
    return db.query(Coupon).filter(Coupon.code == cleaned).first()


def code_exists(db: Session, code: str, exclude_id: int | None = None) -> bool:
    cleaned = code.strip().upper()
    query = db.query(Coupon).filter(Coupon.code == cleaned)
    if exclude_id is not None:
        query = query.filter(Coupon.id != exclude_id)
    return query.first() is not None


def add(db: Session, coupon: Coupon) -> Coupon:
    db.add(coupon)
    db.flush()
    return coupon


def delete(db: Session, coupon: Coupon) -> None:
    db.delete(coupon)
    db.flush()
