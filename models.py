# backend/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric
from .database import Base  # 同階層なら from .database ではなく相対不要（実行の仕方によりどちらでもOK）
from sqlalchemy.orm import relationship

class Product(Base):
    __tablename__ = "商品マスタ"   # ← ここを間違えない
    PRD_ID = Column(Integer, primary_key=True, autoincrement=True)
    CODE   = Column(String(13), unique=True, nullable=False)  # VARCHAR(13)
    NAME   = Column(String(50), nullable=False)
    PRICE  = Column(Integer, nullable=False)

class Transaction(Base):
    __tablename__ = "取引"
    id = Column(Integer, primary_key=True, autoincrement=True)
    emp_cd = Column(String(16), nullable=False)
    store_cd = Column(String(16), nullable=False)
    pos_no = Column(String(16), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)

    details = relationship("TransactionDetail", backref="tx", cascade="all, delete-orphan")

class TransactionDetail(Base):
    __tablename__ = "取引明細"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_id = Column(Integer, ForeignKey("取引.id"), nullable=False)
    product_code = Column(String(32), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)