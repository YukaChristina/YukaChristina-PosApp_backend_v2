from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from decimal import Decimal
import logging

from database import get_db
from models import Product, Transaction, TransactionDetail
from schemas import PurchaseIn as PurchaseRequest, PurchaseOut as PurchaseResponse

router = APIRouter(prefix="", tags=["purchase"])
logger = logging.getLogger(__name__)

@router.post("/purchase2", response_model=PurchaseResponse)
def purchase2(req: PurchaseRequest, db: Session = Depends(get_db)):
    try:
        # 1) リクエストのコード一覧
        codes = [i.code for i in req.items]

        # 2) 商品取得（※列名は大文字：CODE/PRICE）
        products = db.query(Product).filter(Product.CODE.in_(codes)).all()
        by_code = {p.CODE: p for p in products}

        # 3) 存在しないコードを検出
        missing = sorted(set(codes) - set(by_code.keys()))
        if missing:
            raise HTTPException(400, detail={"message": "存在しない商品コード", "codes": missing})

        # 4) 合計金額（税抜）を計算（PRICEは整数想定）
        total_ex_tax = Decimal(0)
        for i in req.items:
            unit_price = Decimal(by_code[i.code].PRICE)
            total_ex_tax += unit_price * i.qty

        # 5) 税込金額を計算
        TAX_RATE = Decimal("0.10")  # 10%消費税
        total_inc_tax = (total_ex_tax * (Decimal("1.0") + TAX_RATE)).quantize(Decimal("1"), rounding="ROUND_HALF_UP")

        # 5) 取引ヘッダ登録（NOT NULLのtotal_amountに必ず値を入れる）
        tx = Transaction(
            emp_cd=req.emp_cd,
            store_cd=req.store_cd,
            pos_no=req.pos_no,
            total_amount=total_inc_tax
        )
        db.add(tx)
        db.flush()  # tx.id を確定させる

        # 6) 取引明細登録（在庫列は無いので操作しない）
        for i in req.items:
            p = by_code[i.code]
            db.add(TransactionDetail(
                tx_id=tx.id,
                product_code=p.CODE,
                qty=i.qty,
                unit_price=p.PRICE
            ))

        db.commit()

        # 7) レスポンス（schemas.PurchaseOutに合わせる）
        return {
            "trd_id": tx.id,
            "total_amt": int(total_inc_tax),   # 税込 or 合計（現状は同じ）
            "ttl_amt_ex_tax": int(total_ex_tax)
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception("purchase2 failed")
        raise HTTPException(status_code=500, detail=f"サーバーエラー: {e.__class__.__name__}: {e}")