from pydantic import BaseModel
from typing import List

class ProductOut(BaseModel):
    code: str
    name: str
    price: int

# 入力側（フロントエンドから受け取るデータ）
class CartItemIn(BaseModel):
    code: str
    qty: int = 1  # デフォルト1

class PurchaseIn(BaseModel):
    items: List[CartItemIn]
    emp_cd: str
    store_cd: str
    pos_no: str

# 出力側（フロントエンドに返すデータ）
class PurchaseOut(BaseModel):
    trd_id: int
    total_amt: int
    ttl_amt_ex_tax: int
