"""Strict standard Base64 conversions. Text uses UTF-8."""
import base64
import binascii


def convert(mode: str, text: str = "", data: bytes = b"") -> dict:
    if mode == "encode-text":
        return {"text": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if mode == "encode-file":
        return {"text": base64.b64encode(data).decode("ascii")}
    if mode not in {"decode-text", "decode-file"}:
        raise ValueError("Choose a supported Base64 operation.")
    try:
        decoded = base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid Base64. Use the standard alphabet and correct padding.") from exc
    if mode == "decode-file":
        return {"base64": base64.b64encode(decoded).decode("ascii"),
                "mime": "application/octet-stream", "extension": "bin", "size": len(decoded)}
    try:
        return {"text": decoded.decode("utf-8")}
    except UnicodeDecodeError as exc:
        raise ValueError("Decoded bytes are not UTF-8 text. Use Base64 → file instead.") from exc
