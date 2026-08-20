import numpy as np
import pandas as pd
import os
from config import DATA_PATH


def load_products() -> list[dict]:
    """
    Load and clean the xlsx dataset.
    Returns a list of dicts with snake_case keys that match
    the field names used by retriever.py.
    """
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found at: {DATA_PATH}")

    df = pd.read_excel(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]

    # Fill nulls
    str_cols = ["Product ID","Category","Product Name","Brand","Model Number",
                "Capacity/Size","Energy Rating","Color","Key Features",
                "Stock Status","Description"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    df["Price (PKR)"]      = pd.to_numeric(df["Price (PKR)"],      errors="coerce").fillna(0)
    df["Warranty (Years)"] = pd.to_numeric(df["Warranty (Years)"], errors="coerce").fillna(0)

    products = []
    for _, row in df.iterrows():
        products.append({
            # snake_case keys used throughout the app
            "product_id":    str(row["Product ID"]).strip(),
            "category":      str(row["Category"]).strip(),
            "product_name":  str(row["Product Name"]).strip(),
            "brand":         str(row["Brand"]).strip(),
            "model_number":  str(row["Model Number"]).strip(),
            "capacity":      str(row["Capacity/Size"]).strip(),
            "energy_rating": str(row["Energy Rating"]).strip(),
            "price_pkr":     int(row["Price (PKR)"]),
            "warranty_years":int(row["Warranty (Years)"]),
            "color":         str(row["Color"]).strip(),
            "key_features":  str(row["Key Features"]).strip(),
            "stock_status":  str(row["Stock Status"]).strip(),
            "description":   str(row["Description"]).strip(),
        })

    print(f"[data_loader] Loaded {len(products)} products.")
    return products