import json
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import openai

MAX_ATTEMPT = 3 # リトライ回数
MIN_SECONDS = 5 # 最小リトライ秒数
MAX_SECONDS = 15 # 最大リトライ秒数

def retry_decorator(func):
    return retry(
        #reraise=True,
        stop=stop_after_attempt(MAX_ATTEMPT),
        wait=wait_exponential(multiplier=1, min=MIN_SECONDS, max=MAX_SECONDS),
        retry=(
            retry_if_exception_type(openai.error.APIError)
            | retry_if_exception_type(openai.error.Timeout)
            | retry_if_exception_type(openai.error.RateLimitError)
            | retry_if_exception_type(openai.error.APIConnectionError)
            | retry_if_exception_type(openai.error.InvalidRequestError)
            | retry_if_exception_type(openai.error.AuthenticationError)
            | retry_if_exception_type(openai.error.ServiceUnavailableError)
        )
    )(func)