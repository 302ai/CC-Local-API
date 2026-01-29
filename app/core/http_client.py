import asyncio
import random
from typing import Any, Iterable, Optional

import aiohttp

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _is_retryable_status(status: int, retry_status: Iterable[int]) -> bool:
    return status in set(retry_status)


def _get_retry_after_seconds(resp: aiohttp.ClientResponse) -> Optional[float]:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)  # 常见情况：秒
    except ValueError:
        return None


async def request_with_retry(
    method: str,
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    retries: int = 3,                 # 失败后额外重试次数（总次数=1+retries）
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    timeout: float | aiohttp.ClientTimeout = 10,
    retry_status: Iterable[int] = RETRY_STATUS,
    retry_on_timeout: bool = True,
    retry_on_connect: bool = True,
    raise_for_status: bool = True,
    **kwargs: Any,
) -> aiohttp.ClientResponse:
    """
    返回 ClientResponse。调用方负责关闭/读取：
      resp = await request_with_retry(...)
      async with resp: ...
    如果 session=None，将临时创建 session；但注意 resp 的生命周期必须在函数内处理
    才能安全关闭 session，所以更推荐用下面的 fetch_* 封装直接返回内容。
    """
    # 这个函数返回 resp，不适合在 session=None 时自动关闭 session（resp 仍在外部使用）
    # 因此：要求 session 不能为空，或你改用 fetch_json/text/bytes。
    if session is None:
        raise ValueError("session=None 时请使用 fetch_json_with_retry / fetch_text_with_retry / fetch_bytes_with_retry 这类返回内容的封装。")

    if isinstance(timeout, (int, float)):
        timeout = aiohttp.ClientTimeout(total=float(timeout))

    last_exc: BaseException | None = None

    for attempt in range(retries + 1):
        try:
            resp = await session.request(method, url, timeout=timeout, **kwargs)

            # 可重试状态码：释放连接再退避
            if _is_retryable_status(resp.status, retry_status) and attempt < retries:
                retry_after = _get_retry_after_seconds(resp)
                await resp.release()

                delay = retry_after if retry_after is not None else min(
                    max_delay,
                    base_delay * (2 ** attempt) + random.uniform(0, 0.2),
                )
                await asyncio.sleep(delay)
                continue

            if raise_for_status:
                resp.raise_for_status()

            return resp

        except asyncio.TimeoutError as e:
            last_exc = e
            if not retry_on_timeout or attempt >= retries:
                raise
        except (aiohttp.ClientConnectorError, aiohttp.ClientOSError) as e:
            last_exc = e
            if not retry_on_connect or attempt >= retries:
                raise
        except aiohttp.ClientResponseError as e:
            last_exc = e
            if (e.status is not None and _is_retryable_status(e.status, retry_status)
                    and attempt < retries):
                delay = min(max_delay, base_delay * (2 ** attempt) + random.uniform(0, 0.2))
                await asyncio.sleep(delay)
                continue
            raise
        except aiohttp.ClientError as e:
            last_exc = e
            if attempt >= retries:
                raise

        if attempt < retries:
            delay = min(max_delay, base_delay * (2 ** attempt) + random.uniform(0, 0.2))
            await asyncio.sleep(delay)

    if last_exc:
        raise last_exc
    raise RuntimeError("request_with_retry: unexpected fallthrough")


async def fetch_json_with_retry(
    method: str,
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    **kwargs: Any,
) -> Any:
    """
    session=None -> 自动创建并在读取完 JSON 后自动关闭
    session!=None -> 复用，不关闭
    """
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()

    try:
        resp = await request_with_retry(method, url, session=session, **kwargs)
        async with resp:
            return await resp.json()
    finally:
        if owns_session:
            await session.close()


async def fetch_text_with_retry(
    method: str,
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    encoding: str | None = None,
    **kwargs: Any,
) -> str:
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()

    try:
        resp = await request_with_retry(method, url, session=session, **kwargs)
        async with resp:
            return await resp.text(encoding=encoding)
    finally:
        if owns_session:
            await session.close()


async def fetch_bytes_with_retry(
    method: str,
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    **kwargs: Any,
) -> bytes:
    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()

    try:
        resp = await request_with_retry(method, url, session=session, **kwargs)
        async with resp:
            return await resp.read()
    finally:
        if owns_session:
            await session.close()
