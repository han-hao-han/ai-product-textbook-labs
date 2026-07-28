# RAG问答保存结果

- 状态：`answered`
- 问题：如何使用Pydantic模型声明请求体？
- Top k：5
- 总耗时：22.498355秒

## 回答

在 FastAPI 中，使用 Pydantic 模型声明请求体的步骤如下：

1. **导入 BaseModel**：从 `pydantic` 导入 `BaseModel`。
2. **创建数据模型**：定义一个继承自 `BaseModel` 的类，并使用 Python 标准类型声明属性。具有默认值（如 `None`）的属性为可选，否则为必选。
3. **声明为参数**：在路径操作函数中，将参数类型声明为该 Pydantic 模型。FastAPI 会自动从请求体中读取 JSON 数据，进行校验并转换为模型实例。

示例代码：

```python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.post("/items/")
async def create_item(item: Item):
    return item
```

在此示例中，`item: Item` 告诉 FastAPI 该参数应从请求体中获取。

## 参考依据

### 请求体

- Chunk：`fastapi_51a712ad620828b3c1cd`
- 来源：https://github.com/fastapi/fastapi/blob/82064857539e6286522c347b4b11331b48dd2378/docs/zh/docs/tutorial/body.md

# 请求体

当你需要从客户端（比如浏览器）向你的 API 发送数据时，会把它作为**请求体**发送。

**请求体**是客户端发送给你的 API 的数据。**响应体**是你的 API 发送给客户端的数据。

你的 API 几乎总是需要发送**响应体**。但客户端不一定总是要发送**请求体**，有时它们只请求某个路径，可能带一些查询参数，但不会发送请求体。

使用 Pydantic 模型来声明**请求体**，能充分利用它的功能和优点。

> **信息**

发送数据应使用以下之一：`POST`（

### 请求体

- Chunk：`fastapi_7f0b0fa681a4f61c5c89`
- 来源：https://github.com/fastapi/fastapi/blob/82064857539e6286522c347b4b11331b48dd2378/docs/zh/docs/tutorial/body.md

# 请求体

## 声明为参数

````python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.post("/items/")
async def create_item(item: Item):
    return item
```

### 请求体

- Chunk：`fastapi_3938c4a4fed740ce48d9`
- 来源：https://github.com/fastapi/fastapi/blob/82064857539e6286522c347b4b11331b48dd2378/docs/zh/docs/tutorial/body.md

# 请求体

## 使用模型

````python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.post("/items/")
async def create_item(item: Item):
    item_dict = item.model_dump()
    if item.tax is not None:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict
```
