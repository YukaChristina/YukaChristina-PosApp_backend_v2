from backend.api.purchase import router as purchase_router
import traceback
from fastapi import FastAPI, Depends, HTTPException, Body, Request
from sqlalchemy.exc import SQLAlchemyError
from fastapi.responses import JSONResponse
import json
from sqlalchemy.orm import Session
from sqlalchemy import text  # ← 後で生SQLを使うので追加
from .database import get_db
from .models import Product
from .schemas import ProductOut, PurchaseIn, PurchaseOut
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import engine  # 既存のengineを利用
import logging

logger = logging.getLogger("uvicorn.error")  # ターミナルに出るuvicornのログ

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- アプリ起動時 ---
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
        logger.info("✅ DB connectivity OK (startup)")
    except Exception as e:
        logger.error("❌ DB connectivity FAILED (startup): %s", e, exc_info=True)
    yield
    # --- アプリ終了時（必要ならリソース解放をここに） ---

# ★ app はここで1回だけ作る（他の場所で再代入しない！）
app = FastAPI(
    title="POS API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(purchase_router)

from backend.api.purchase import router as purchase_router

# CORS設定（Next.jsのフロントエンドから呼び出せるようにする）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],  # Next.jsのデフォルトポート
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== ルート ==========
@app.get("/products/search", response_model=ProductOut)
def search_product(code: str, db: Session = Depends(get_db)):
    # 1) DB検索（最初の1件）→SQLAlchemyのクエリ
    row = db.query(Product).filter(Product.CODE == code).first()

    # 2) なければ 404
    if row is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    # 3) あれば整形して返す（キー名は小文字で返す）
    return ProductOut(code=row.CODE, name=row.NAME, price=row.PRICE)

'''# 4) 購入処理（エコー）
@app.post("/purchase2")
def purchase2(body: PurchaseIn, db: Session = Depends(get_db)): #FastAPIがSQLAlchemyのSession(=DB接続のためのハンドル)を自動で用意してくれている
    #1) バリデーション
    if not body.items:
        raise HTTPException(status_code=400, detail="購入アイテムが空です")
    if any(item.qty <= 0 for item in body.items):
        raise HTTPException(status_code=400, detail="数量は1以上である必要があります")
    
    # 4) 取引登録（トランザクション）
    try:
        with db.begin():  # ← 成功で自動コミット、例外で自動ロールバック,db.begin()はトランザクション開始・終了を自動制御する構文
            #2) 商品コードを引き当てる（DB検索）
            resolved = []  # (product_row, qty) の配列
            for it in body.items:
                p = db.query(Product).filter(Product.CODE == it.code).first()
                if p is None:
                    raise HTTPException(status_code=404, detail=f"商品コードが見つかりません: {it.code}")
                resolved.append((p, it.qty))

            #3) 合計金額計算（PRICEは税込み単価）
            total = sum(p.PRICE * qty for p, qty in resolved)  # 合計金額計
            ex_tax = round(total / 1.1)  # 税抜金額（端数四捨五入）
            #return {"total": total, "ex_tax": ex_tax}
            
            # 4-1) 「取引」テーブルにヘッダ INSERT
            db.execute( #db.execute()はSQLAlchemyの生SQL実行メソッド。テーブル名が日本語なので生SQLじゃないとINSERTできない。
                text("""
                    INSERT INTO `取引` (EMP_CD, STORE_CD, POS_NO, TOTAL_AMT, TTL_AMT_EX_TAX)
                    VALUES (:emp_cd, :store_cd, :pos_no, :total, :ex_tax)
                """),
                {
                    "emp_cd": body.emp_cd,
                    "store_cd": body.store_cd,
                    "pos_no": body.pos_no,
                    "total": total,
                    "ex_tax": ex_tax, 
                },
            )
            # 4-2) 自動採番 TRD_ID を取得（同一コネクション限定で有効）→MySQLサーバに複数のクライアントが接続していても、INSERTしたIDが混ざらないような仕組み
            trd_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar() #LAST_INSERT_ID()はMySQLの（既存の）関数で、直前のINSERTで自動採番されたIDを取得する

            # 4-3) 明細 INSERT（数量ぶん複写）各商品の明細を登録（数量ぶん繰り返す）
            dtl_id = 1
            for p, qty in resolved:
                for _ in range(qty):
                    db.execute(#こちらもテーブル名が日本語なので生SQLでINSERT
                        text("""
                            INSERT INTO `取引明細`
                            (TRD_ID, DTL_ID, PRD_ID, PRD_CODE, PRD_NAME, PRD_PRICE, TAX_CD)
                            VALUES
                            (:trd_id, :dtl_id, :prd_id, :prd_code, :prd_name, :prd_price, :tax_cd)
                        """),
                        {
                            "trd_id": trd_id,
                            "dtl_id": dtl_id,
                            "prd_id": p.PRD_ID,
                            "prd_code": p.CODE,
                            "prd_name": p.NAME,
                            "prd_price": p.PRICE,
                            "tax_cd": "10",  # MVPは10%固定
                        },
                    )
                    dtl_id += 1

        # 5) 正常終了 → Pydanticで“検品して”返す
        print("[E] return")
        return PurchaseOut(trd_id=trd_id, total_amt=total, ttl_amt_ex_tax=ex_tax)

    #except HTTPException as e:
        #raise
    except SQLAlchemyError as e:
        # 失敗時は with db.begin() が自動でロールバック
        print("===DB error===")
        traceback.print_exc()
        print("orig:", getattr(e, "orig", None))  # 元のDB例外
        raise HTTPException(status_code=500, detail = "購入処理に失敗しました")
    except Exception as e:
        print("===Unexpected===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail = "購入処理に失敗しました")'''


#app = FastAPI(lifespan=lifespan)

@app.get("/health/db")
def health_db():
        """ヘルスチェック用：DBにSELECT 1してOK/NGを返す"""
        try:
            with engine.connect() as con:
                con.execute(text("SELECT 1"))
            return {"db": "ok"}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"db not ok: {e}")
        
@app.get("/") 
def root(): return {"status": "ok"}