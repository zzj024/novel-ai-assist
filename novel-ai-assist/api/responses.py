"""统一 API 响应格式

职责：
- 提供 ok() / err() 两个工厂函数，生成统一的 JSON 信封
- 所有 API 端点必须使用这两个函数返回，确保前端消费一致性

信封格式：
    成功 -> {"ok": true,  "data": <any>, "error": null}
    失败 -> {"ok": false, "data": null,  "error": <str>}
"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def ok(*, data: Any, status_code: int = 200) -> JSONResponse:
    """成功响应
    用法:
        return ok(data=chapter)
        return ok(data=[], status_code=200)
    """

    return JSONResponse(
        status_code=status_code,
        content={"ok": True, "data": jsonable_encoder(data), "error": None})

def err(message: str, status_code: int = 400) -> JSONResponse:
    """错误响应
    用法:
        return err("章节不存在", status_code=404)
        return err("参数校验失败", status_code=422)
    """

    return JSONResponse(
        status_code=status_code, 
        content={"ok": False, "data": None, "error": message})