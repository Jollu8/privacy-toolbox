"""Remove known tracking keys without rewriting retained query values."""
from urllib.parse import unquote_plus, urlsplit, urlunsplit

TRACKERS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
            "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid"}


def clean_url(url: str, remove_ref: bool = False) -> dict:
    url = url.strip()
    if any(ord(char) < 32 for char in url):
        raise ValueError("The URL contains control characters.")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Enter a complete HTTP or HTTPS URL.")
    # Validate the port too; urlsplit otherwise allows malformed ports.
    _ = parts.port
    kept, removed = [], []
    for pair in parts.query.split("&") if parts.query else []:
        key = unquote_plus(pair.split("=", 1)[0])
        if key.lower() in TRACKERS or (remove_ref and key.lower() in {"ref", "referrer"}):
            removed.append(key)
        else:
            kept.append(pair)
    return {"text": urlunsplit(parts._replace(query="&".join(kept))), "removed": removed}
