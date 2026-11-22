from datetime import datetime

from sqlalchemy.orm import Session

from app.models.payment_proof import PaymentProof


def get_for_order(db: Session, order_id: int) -> PaymentProof | None:
    return db.query(PaymentProof).filter(PaymentProof.order_id == order_id).first()


def add(db: Session, proof: PaymentProof) -> PaymentProof:
    db.add(proof)
    db.flush()
    return proof


def delete_expired(db: Session, now: datetime) -> int:
    """Borra los comprobantes que vencieron hasta `now` y devuelve cuántos eran."""
    return db.query(PaymentProof).filter(PaymentProof.expires_at <= now).delete(synchronize_session=False)
