import hashlib


def short_hash(input_str: str, length: int = 16) -> str:
    """
    Encrypt/hash the input string as a string with a specified number of bits (default 16 bits)
    Suitable for generate IDs, folder names, or desensitization
    """
    # CALCULATE MD5
    md5_obj = hashlib.md5(input_str.encode('utf-8'))
    # Get a 32-bit hexadecimal string
    full_hash = md5_obj.hexdigest()
    # Intercept the specified number of digits
    return full_hash[:length]