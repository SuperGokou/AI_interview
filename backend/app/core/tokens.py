"""link-token 生成(单一职责:URL 安全随机 token)。"""

import secrets


def generate_link_token(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)
