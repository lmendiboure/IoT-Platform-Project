import hmac, hashlib, json, time

def canonical_json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

def verify_hmac(key: bytes, payload: dict) -> bool:
    if "hmac" not in payload:
        return False
    tag = payload["hmac"]
    payload_wo = dict(payload)
    payload_wo.pop("hmac", None)
    msg = canonical_json(payload_wo).encode("utf-8")
    expected = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, tag)

def verify_freshness(payload: dict, max_age_ms: int = 5000) -> bool:
    ts = payload.get("ts_ms")
    if ts is None:
        return False
    now = int(time.time() * 1000)
    return abs(now - int(ts)) <= max_age_ms
