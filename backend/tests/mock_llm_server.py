import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


app = FastAPI()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    if payload.get("stream"):
        async def events():
            for token in ["这是", "一条", "流式回复。"]:
                chunk = {
                    "id": "mock-stream",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "mock-model",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final = {
                "id": "mock-stream",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "mock-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return JSONResponse(
        {
            "id": "mock-completion",
            "object": "chat.completion",
            "created": 0,
            "model": "mock-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "[]"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
