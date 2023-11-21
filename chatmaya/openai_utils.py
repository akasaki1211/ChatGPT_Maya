from typing import List

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
)
import tiktoken

client = OpenAI()

CHAT_MODELS = [
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo",
    "gpt-4-1106-preview",
    "gpt-4"
]
DEFAULT_CHAT_MODEL = CHAT_MODELS[0]

DEFAULT_ENCODING = "cl100k_base"

def num_tokens_from_text(text:str, encoding_name:str=DEFAULT_ENCODING) -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

def chat_completion_stream(messages:List, model:str=DEFAULT_CHAT_MODEL, **kwargs) -> ChatCompletionMessage:

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        **kwargs
    )

    for chunk in response:
        if chunk:
            content = chunk.choices[0].delta.content
            if content:
                yield content