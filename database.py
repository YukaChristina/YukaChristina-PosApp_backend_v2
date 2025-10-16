# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

# .env 読み込み
load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("環境変数 DB_URL が見つかりません。'.env' を確認してください。")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# SQLAlchemy接続URL
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

#SSL証明書のパス
ssl_cert = os.path.join(os.path.dirname(__file__), "certs", 'DigiCertGlobalRootG2.crt.pem')

# エンジン作成（落ちた接続を自動復旧）
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    echo=False,  # 必要なら True にしてSQLログを見る
    connect_args={
        "ssl": {"ca":ssl_cert} 
    },
    future = True,
)

# セッションファクトリ
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# 今後モデル定義で継承する Base
class Base(DeclarativeBase):
    pass

# FastAPI で使う依存関数（後でそのまま使える）main.pyで利用する。DBとの接続を一時的に開いて、使い終わったら閉じるための関数
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===== 接続トラブル特定用: 段階別ヘルスチェック =====
'''if __name__ == "__main__":
    import os, socket, traceback, pathlib
    import pymysql
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError, InterfaceError, ProgrammingError, SQLAlchemyError
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from .models import Product

    # ---- 0) 事前チェック（環境変数・証明書・URL整合） ----
    print("=== Step 0: 環境変数・証明書の存在確認 ===")
    def _mask(s: str, keep=4):
        if not s: return "<EMPTY>"
        return s[:keep] + "…" if len(s) > keep else "****"

    print("DB_URL       :", _mask(os.getenv("DB_URL", "")))
    print("DB_USER      :", _mask(os.getenv("DB_USER", "")))
    print("DB_PASSWORD  :", _mask(os.getenv("DB_PASSWORD", "")))
    print("DB_HOST      :", os.getenv("DB_HOST", ""))
    print("DB_PORT      :", os.getenv("DB_PORT", ""))
    print("DB_NAME      :", os.getenv("DB_NAME", ""))

    # 注意: あなたのengineは DB_URL を使っています（DATABASE_URLは未使用）
    # 必要なら DATABASE_URL と DB_URL を統一してください。
    print("engine uses  :", "DB_URL")

    print(f"SSL cert path: {ssl_cert}")
    if not pathlib.Path(ssl_cert).exists():
        print("❌ 証明書ファイルが見つかりません。パスを確認してください。")
    else:
        print("✅ 証明書ファイルあり。")

    # ---- 1) DNS解決（ホストに辿り着けるか） ----
    print("\n=== Step 1: DNS解決 ===")
    host = os.getenv("DB_HOST", "")
    try:
        ip = socket.gethostbyname(host)
        print(f"✅ {host} -> {ip}")
    except Exception as e:
        print("❌ ホスト名解決に失敗:", e)

    # ---- 2) PyMySQL での素の接続（SQLAlchemy抜き） ----
    print("\n=== Step 2: PyMySQL生接続（SSL含む） ===")
    try:
        conn = pymysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", "3306")),
            ssl={"ca": ssl_cert},          # ← ここが正です（二重の "ssl":{ "ssl":{…}} はNG）
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print("✅ PyMySQL: SELECT 1 成功")
        conn.close()
    except Exception as e:
        print("❌ PyMySQL接続（またはSSL）で失敗:")
        traceback.print_exc()

    # ---- 3) SQLAlchemyエンジン接続（SELECT 1） ----
    print("\n=== Step 3: SQLAlchemy engine.connect() ===")
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
            print("✅ SQLAlchemy: SELECT 1 成功")
    except (OperationalError, InterfaceError) as e:
        print("❌ SQLAlchemy: 接続層(ネットワーク/認証/SSL)で失敗")
        traceback.print_exc()
    except ProgrammingError as e:
        print("❌ SQLAlchemy: SQL文/スキーマで失敗")
        traceback.print_exc()
    except SQLAlchemyError as e:
        print("❌ SQLAlchemy: その他のSQLAlchemy例外")
        traceback.pri

    # ---- 4) ORMで商品マスタを読み出し ----
    print("\n=== Step 4: ORMで商品マスタ読み出し ===")
    try:
        with Session(engine) as s:
            rows = s.execute(select(Product).limit(5)).scalars().all()
            print(f"✅ 読み出し成功。件数: {len(rows)}")
            for p in rows:
                print(p.PRD_ID, p.CODE, p.NAME, p.PRICE)
    except Exception:
        print("❌ ORM: 商品マスタ読み出しでエラー")
        traceback.print_exc()

    print("\n=== 診断完了 ===")

    # ① テーブル作成（モデル通りに Azure 側へ作る）
    print("\n=== Create tables on Azure (if not exists) ===")
    from .models import Base, Product
    Base.metadata.create_all(bind=engine)
    print("✅ created (or already exists)")

    # ② 1件だけ挿入して存在確認
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    with Session(engine) as s:
        # 既に同じCODEがあると重複エラーになるので存在チェック
        exists = s.execute(select(Product).where(Product.CODE == "4900000000000")).scalar()
        if not exists:
            s.add(Product(CODE="4900000000000", NAME="接続確認アイテム", PRICE=1))
            s.commit()
            print("✅ inserted 1 row for sanity check")

    # ③ 生SQLとORMの両方で見えるか確認
    from sqlalchemy import text
    with engine.connect() as con:
        rows = con.execute(text("SHOW FULL TABLES")).all()
        print("TABLES after create:", [r[0] for r in rows if r and r[0]])

    with Session(engine) as s:
        rows = s.execute(select(Product).limit(5)).scalars().all()
        print(f"✅ ORM read OK. count={len(rows)}")
        for p in rows:
            print(p.PRD_ID, p.CODE, p.NAME, p.PRICE)'''
