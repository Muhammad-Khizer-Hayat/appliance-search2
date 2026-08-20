import os
from flask import Flask
from flask_cors import CORS

from config import FLASK_DEBUG, FLASK_PORT
from core.data_loader import load_products
from core.faiss_store import build_and_save_index, load_index, index_is_valid
from routes.index_routes import index_bp
from routes.search_routes import search_bp
from routes.admin_routes import admin_bp, SECRET_KEY


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.secret_key = SECRET_KEY

    app.register_blueprint(index_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)

    # Load products
    products = load_products()

    # Build or load FAISS index
    if index_is_valid():
        try:
            print("[app] Loading existing FAISS index ...")
            index, products = load_index()
        except Exception as e:
            print(f"[app] Index load failed ({e}) — rebuilding ...")
            index = build_and_save_index(products)
    else:
        print("[app] Building FAISS index from scratch ...")
        for path in (__import__('config').FAISS_INDEX_PATH,
                     __import__('config').PRODUCTS_PKL_PATH):
            if os.path.exists(path):
                os.remove(path)
        index = build_and_save_index(products)

    app.products    = products
    app.faiss_index = index

    print(f"[app] Ready — {len(products)} products · FAISS {index.ntotal} vectors")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=FLASK_DEBUG, port=FLASK_PORT)