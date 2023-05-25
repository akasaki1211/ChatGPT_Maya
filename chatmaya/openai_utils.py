# -*- coding: utf-8 -*-
from typing import List
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import openai
import tiktoken

DEFAULT_CHAT_MODEL = "gpt-3.5-turbo"
DEFAULT_ENCODING = "cl100k_base"

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

def num_tokens_from_text(text:str, encoding_name:str=DEFAULT_ENCODING) -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

@retry_decorator
def chat_completion_stream(messages:List, model:str=DEFAULT_CHAT_MODEL, **kwargs) -> str:
        
        result = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        
        for chunk in result:
            if chunk:
                content = chunk['choices'][0]['delta'].get('content')
                if content:
                    yield content