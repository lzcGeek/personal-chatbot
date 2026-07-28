from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError


@dataclass(frozen=True)
class ChatFailure(Exception):
    code: str
    user_message: str
    recoverable: bool

    def __str__(self) -> str:
        return self.user_message


def classify_chat_failure(exc: Exception) -> ChatFailure:
    if isinstance(exc, ChatFailure):
        return exc
    if isinstance(exc, RateLimitError):
        return ChatFailure("llm_rate_limited", "服务繁忙，请稍后重试。", True)
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return ChatFailure("llm_timeout", "生成响应超时，请重试。", True)
    if isinstance(exc, APIConnectionError):
        return ChatFailure("llm_unavailable", "生成服务暂时不可用，请稍后重试。", True)
    if isinstance(exc, APIStatusError):
        if exc.status_code >= 500:
            return ChatFailure("llm_unavailable", "生成服务暂时不可用，请稍后重试。", True)
        return ChatFailure("llm_request_rejected", "生成请求未被服务接受，请检查配置。", False)
    return ChatFailure("generation_failed", "生成失败，请稍后重试。", True)


def is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError, TimeoutError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500
