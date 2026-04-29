import json
import os
from pathlib import Path

USERS_FILE = Path(__file__).parent / "users.json"

def load_users(path=USERS_FILE):
    if not os.path.exists(path):
        # Create default users.json if not exists
        default_users = {
            "hapew": {
                "name": "하프",
                "capital_krw": 20000000,
                "risk_tolerance": "normal",
                "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
                "assets": ["SPY", "TLT"],
                "active": True
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2, ensure_ascii=False)
        return default_users
        
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_user_config(user_id, base_config):
    """
    Merges user risk_tolerance into base config RP_CAPS.
    
    conservative: ELEVATED SPY max 50%, CRISIS SPY max 20%
    normal:       ELEVATED SPY max 65%, CRISIS SPY max 35% (default)
    aggressive:   ELEVATED SPY max 80%, CRISIS SPY max 50%
    """
    users = load_users()
    if user_id not in users:
        return base_config
        
    user = users[user_id]
    risk = user.get("risk_tolerance", "normal")
    
    # Clone the config to avoid modifying the global one
    import copy
    config = copy.deepcopy(base_config)
    
    # Adjust RP_CAPS based on risk tolerance
    if risk == "conservative":
        config.RP_CAPS["ELEVATED"]["SPY_MAX"] = 0.50
        config.RP_CAPS["CRISIS"]["SPY_MAX"] = 0.20
    elif risk == "aggressive":
        config.RP_CAPS["ELEVATED"]["SPY_MAX"] = 0.80
        config.RP_CAPS["CRISIS"]["SPY_MAX"] = 0.50
    # "normal" uses base_config values (0.65 and 0.35)
    
    return config

if __name__ == "__main__":
    users = load_users()
    print(f"Loaded {len(users)} users.")
    for uid, u in users.items():
        print(f" - {u['name']} ({uid}): {u['risk_tolerance']}")
