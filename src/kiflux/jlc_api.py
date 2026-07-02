import json
import urllib.request
import urllib.error
import logging

JLCPCB_SEARCH_API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"

def fetch_jlcpcb_part_data(lcsc_code):
    """
    Queries the public JLCPCB search API to retrieve component library type (Basic/Extended),
    stock count, and progressive price breaks.
    Returns:
        dict: A dictionary containing 'library_type' (Basic/Extended), 'price_breaks' (list of dicts),
              and 'stock' (int). Returns None on error or if part is not found.
    """
    lcsc_code = lcsc_code.upper().strip()
    payload = {
        "keyword": lcsc_code,
        "currentPage": 1,
        "pageSize": 10
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://jlcpcb.com/parts"
    }
    
    try:
        req = urllib.request.Request(
            url=JLCPCB_SEARCH_API,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )
        # Timeout de 10s para não travar eternamente se a rede falhar
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = json.loads(response.read().decode("utf-8"))
            
        component_data = raw.get("data", {}).get("componentPageInfo", {}).get("list", [])
        if not component_data:
            return None
            
        # Pega a correspondência exata do LCSC
        item = None
        for entry in component_data:
            if entry.get("componentCode", "").upper().strip() == lcsc_code:
                item = entry
                break
                
        if not item:
            item = component_data[0] # Fallback para o primeiro resultado
            
        lib_type = "Basic" if item.get("componentLibraryType") == "base" else "Extended"
        stock = item.get("stockCount", 0)
        
        prices_list = item.get("componentPrices") or []
        price_breaks = []
        for p in prices_list:
            qty = p.get("startNumber", 1)
            price = p.get("productPrice")
            if price is not None:
                price_breaks.append({
                    "qty": int(qty),
                    "price": float(price)
                })
                
        return {
            "library_type": lib_type,
            "stock": int(stock),
            "price_breaks": price_breaks,
            "describe": item.get("describe", "")
        }
    except Exception as e:
        logging.warning(f"Failed to fetch JLCPCB data for {lcsc_code}: {e}")
        return None

def search_jlcpcb_components(keyword, page_size=20, part_type=None):
    """
    Searches for components on the JLCPCB SMT library by keyword.
    Returns a list of dicts.
    """
    keyword = keyword.strip()
    payload = {
        "keyword": keyword,
        "currentPage": 1,
        "pageSize": page_size
    }
    if part_type:
        payload["componentLibraryType"] = part_type
        
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://jlcpcb.com/parts"
    }
    try:
        req = urllib.request.Request(
            url=JLCPCB_SEARCH_API,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = json.loads(response.read().decode("utf-8"))
            
        items = raw.get("data", {}).get("componentPageInfo", {}).get("list", [])
        results = []
        for item in items:
            prices = item.get("componentPrices") or []
            unit_price = prices[0].get("productPrice") if prices else 0.0
            results.append({
                "lcsc": item.get("componentCode", ""),
                "name": item.get("componentName", ""),
                "model": item.get("componentModelEn", ""),
                "brand": item.get("componentBrandEn", ""),
                "package": item.get("componentSpecificationEn", ""),
                "stock": int(item.get("stockCount", 0)),
                "type": "Basic" if item.get("componentLibraryType") == "base" else "Extended",
                "price": float(unit_price) if unit_price is not None else 0.0,
                "description": item.get("describe", "")
            })
        return results
    except Exception as e:
        logging.warning(f"JLCPCB search failed for '{keyword}': {e}")
        return []
