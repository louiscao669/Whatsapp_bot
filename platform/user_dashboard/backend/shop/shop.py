def shop_view(store):
    items = list((store or {}).get("items") or [])
    return {
        "tools": [item for item in items if item.get("item_type") != "cosmetic"],
        "decorations": [item for item in items if item.get("item_type") == "cosmetic"],
    }
