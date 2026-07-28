# 检查点2报告：模型、索引与Top 5

## 状态

```text
warning
```

## 本地Embedding模型

- 模型：`Qwen/Qwen3-Embedding-0.6B`
- Revision：`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- License：Apache-2.0
- 设备：cpu
- 维度：1024
- 池化：last_non_padding_token
- 归一化：L2
- 查询任务指令：Given a Chinese question about FastAPI, retrieve relevant passages from the FastAPI Chinese documentation that answer the question.

## NumPy索引

- 矩阵形状：[400, 1024]
- dtype：float32
- Chunk顺序哈希：`71cf57bca05ddbc43a61a6155690f5bd4ebc07cc1cf6f181fe80bfc2d66e741d`
- 索引哈希：`250ddaea4e54c67d0de36af64afe66667794d3c0100ecf73706e1ad115262909`
- 最大输入Token：2829
- 截断输入：0
- 构建耗时：911.116234秒

## 固定问题

如何使用Pydantic模型声明请求体？

## 精确余弦Top 5

### Top 1：请求体

- Score：0.862075
- Chunk ID：`fastapi_51a712ad620828b3c1cd`
- 来源：`docs/zh/docs/tutorial/body.md`
- 章节：请求体 { #request-body }
- Chunk序号：0
- 含代码：True

# 请求体

当你需要从客户端（比如浏览器）向你的 API 发送数据时，会把它作为**请求体**发送。

**请求体**是客户端发送给你的 API 的数据。**响应体**是你的 API 发送给客户端的数据。

你的 API 几乎总是需要发送**响应体**。但客户端不一定总是要发送**请求体**，有时它们只请求某个路径，可能带一些查询参数，但不会发送请求体。

使用 Pydantic 模型来声明**请求体**，能充分利用它的功能和优点。

> **信息**

发送数据应使用以下之一：`POST`（最常见）、`PUT`、`DELETE` 或 `PATCH`。

规范中没有定义用 `GET` 请求发送请求体的行为，但 FastAPI 仍支持这种方式，只用于非常复杂/极端的用例。

由于不推荐，在使用 `GET` 时，Swagger UI 的交互式文档不会显示请求体的文档，而且中间的代理可能也不支持它。

## 导入 Pydantic 的 `BaseModel`

从 `pydantic` 中导入 `BaseModel`：

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
````

## 创建数据模型

把数据模型声明为继承 `BaseModel` 的类。

使用 Python 标准类型声明所有属性：

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
````

与声明查询参数一样，包含默认值的模型属性是可选的，否则就是必选的。把默认值设为 `None` 可使其变为可选。

例如，上述模型声明如下 JSON "object"（即 Python `dict`）：

```JSON
{
    "name": "Foo",
    "description": "An optional description",
    "price": 45.2,
    "tax": 3.5
}
```

...由于 `description` 和 `tax` 是可选的（默认值为 `None`），下面的 JSON "object" 也有效：

```JSON
{
    "name": "Foo",
    "price": 45.2
}
```

## 声明为参数

使用与声明路径和查询参数相同的方式，把它添加至*路径操作*：

### Top 2：请求体

- Score：0.822841
- Chunk ID：`fastapi_7f0b0fa681a4f61c5c89`
- 来源：`docs/zh/docs/tutorial/body.md`
- 章节：请求体 { #request-body } > 声明为参数 { #declare-it-as-a-parameter }
- Chunk序号：1
- 含代码：True

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
````

...并把其类型声明为你创建的模型 `Item`。

## 结果

仅使用这些 Python 类型声明，**FastAPI** 就可以：

* 以 JSON 形式读取请求体。
* （在必要时）把请求体转换为对应的类型。
* 校验数据。
    * 数据无效时返回清晰的错误信息，并指出错误数据的确切位置和内容。
* 把接收的数据赋值给参数 `item`。
    * 因为你把函数中的参数类型声明为 `Item`，所以还能获得所有属性及其类型的编辑器支持（补全等）。
* 为你的模型生成 JSON Schema 定义，如果对你的项目有意义，还可以在其他地方使用它们。
* 这些 schema 会成为生成的 OpenAPI Schema 的一部分，并被自动文档的 UIs 使用。

## 自动文档

你的模型的 JSON Schema 会成为生成的 OpenAPI Schema 的一部分，并显示在交互式 API 文档中：

[图片]

并且，还会用于需要它们的每个*路径操作*的 API 文档中：

[图片]

## 编辑器支持

在编辑器中，函数内部你会在各处得到类型提示与补全（如果接收的不是 Pydantic 模型，而是 `dict`，就不会有这样的支持）：

[图片]

还支持检查错误的类型操作：

[图片]

这并非偶然，整个框架都是围绕这种设计构建的。

并且在设计阶段、实现之前就进行了全面测试，以确保它能在所有编辑器中正常工作。

我们甚至对 Pydantic 本身做了一些改动以支持这些功能。

上面的截图来自 Visual Studio Code。

但使用 PyCharm 和大多数其他 Python 编辑器，你也会获得相同的编辑器支持：

[图片]

> **提示**

如果你使用 PyCharm 作为编辑器，可以使用 Pydantic PyCharm 插件。

它能改进对 Pydantic 模型的编辑器支持，包括：

* 自动补全
* 类型检查
* 代码重构
* 查找
* 代码审查

## 使用模型

在*路径操作*函数内部直接访问模型对象的所有属性：

### Top 3：请求体

- Score：0.790299
- Chunk ID：`fastapi_3938c4a4fed740ce48d9`
- 来源：`docs/zh/docs/tutorial/body.md`
- 章节：请求体 { #request-body } > 使用模型 { #use-the-model }
- Chunk序号：2
- 含代码：True

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
````

## 请求体 + 路径参数

可以同时声明路径参数和请求体。

**FastAPI** 能识别与**路径参数**匹配的函数参数应该**从路径中获取**，而声明为 Pydantic 模型的函数参数应该**从请求体中获取**。

````python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item):
    return {"item_id": item_id, **item.model_dump()}
````

## 请求体 + 路径 + 查询参数

也可以同时声明**请求体**、**路径**和**查询**参数。

**FastAPI** 会分别识别它们，并从正确的位置获取数据。

````python
from fastapi import FastAPI
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

app = FastAPI()

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item, q: str | None = None):
    result = {"item_id": item_id, **item.model_dump()}
    if q:
        result.update({"q": q})
    return result
````

函数参数按如下规则进行识别：

* 如果该参数也在**路径**中声明了，它就是路径参数。
* 如果该参数是（`int`、`float`、`str`、`bool` 等）**单一类型**，它会被当作**查询**参数。
* 如果该参数的类型声明为 **Pydantic 模型**，它会被当作请求**体**。

> **注意**

FastAPI 会根据默认值 `= None` 知道 `q` 的值不是必填的。

`str | None` 并不是 FastAPI 用来判断是否必填的依据；是否必填由是否有默认值 `= None` 决定。

### Top 4：请求体 - 字段

- Score：0.777638
- Chunk ID：`fastapi_4eb8b9a92e49c814e7a8`
- 来源：`docs/zh/docs/tutorial/body-fields.md`
- 章节：请求体 - 字段 { #body-fields }
- Chunk序号：0
- 含代码：True

# 请求体 - 字段

与在*路径操作函数*中使用 `Query`、`Path` 、`Body` 声明校验与元数据的方式一样，可以使用 Pydantic 的 `Field` 在 Pydantic 模型内部声明校验和元数据。

## 导入 `Field`

首先，从 Pydantic 中导入 `Field`：

````python
from typing import Annotated

from fastapi import Body, FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str | None = Field(
        default=None, title="The description of the item", max_length=300
    )
    price: float = Field(gt=0, description="The price must be greater than zero")
    tax: float | None = None

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Annotated[Item, Body(embed=True)]):
    results = {"item_id": item_id, "item": item}
    return results
````

> **警告**

注意，与从 `fastapi` 导入 `Query`，`Path`、`Body` 不同，要直接从 `pydantic` 导入 `Field` 。

## 声明模型属性

然后，使用 `Field` 定义模型的属性：

````python
from typing import Annotated

from fastapi import Body, FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str | None = Field(
        default=None, title="The description of the item", max_length=300
    )
    price: float = Field(gt=0, description="The price must be greater than zero")
    tax: float | None = None

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Annotated[Item, Body(embed=True)]):
    results = {"item_id": item_id, "item": item}
    return results
````

`Field` 的工作方式和 `Query`、`Path`、`Body` 相同，参数也相同。

> **技术细节**

实际上，`Query`、`Path` 以及你接下来会看到的其它对象，会创建公共 `Param` 类的子类的对象，而 `Param` 本身是 Pydantic 中 `FieldInfo` 的子类。

Pydantic 的 `Field` 返回也是 `FieldInfo` 的类实例。

`Body` 直接返回的也是 `FieldInfo` 的子类的对象。后文还会介绍一些 `Body` 的子类。

注意，从 `fastapi` 导入的 `Query`、`Path` 等对象实际上都是返回特殊类的函数。

> **提示**

### Top 5：表单模型

- Score：0.768669
- Chunk ID：`fastapi_c1348465d3b3f125f455`
- 来源：`docs/zh/docs/tutorial/request-form-models.md`
- 章节：表单模型 { #form-models }
- Chunk序号：0
- 含代码：True

# 表单模型

你可以在 FastAPI 中使用 **Pydantic 模型**声明**表单字段**。

> **信息**

要使用表单，首先安装 `python-multipart`。

确保你创建一个[虚拟环境](https://github.com/fastapi/fastapi/blob/82064857539e6286522c347b4b11331b48dd2378/docs/zh/docs/virtual-environments.md)，激活它，然后再安装，例如：

```console
$ pip install python-multipart
```

> **注意**

自 FastAPI 版本 `0.113.0` 起支持此功能。🤓

## 表单的 Pydantic 模型

你只需声明一个 **Pydantic 模型**，其中包含你希望接收的**表单字段**，然后将参数声明为 `Form`：

````python
from typing import Annotated

from fastapi import FastAPI, Form
from pydantic import BaseModel

app = FastAPI()

class FormData(BaseModel):
    username: str
    password: str

@app.post("/login/")
async def login(data: Annotated[FormData, Form()]):
    return data
````

**FastAPI** 将从请求中的**表单数据**中**提取**出**每个字段**的数据，并提供你定义的 Pydantic 模型。

## 检查文档

你可以在文档 UI 中验证它，地址为 `/docs`：

[图片]

## 禁止额外的表单字段

在某些特殊使用情况下（可能并不常见），你可能希望将表单字段**限制**为仅在 Pydantic 模型中声明过的字段，并**禁止**任何**额外**的字段。

> **注意**

自 FastAPI 版本 `0.114.0` 起支持此功能。🤓

你可以使用 Pydantic 的模型配置来 `forbid` 任何 `extra` 字段：

````python
from typing import Annotated

from fastapi import FastAPI, Form
from pydantic import BaseModel

app = FastAPI()

class FormData(BaseModel):
    username: str
    password: str
    model_config = {"extra": "forbid"}

@app.post("/login/")
async def login(data: Annotated[FormData, Form()]):
    return data
````

如果客户端尝试发送一些额外的数据，他们将收到**错误**响应。

例如，客户端尝试发送如下表单字段：

* `username`: `Rick`
* `password`: `Portal Gun`
* `extra`: `Mr. Poopybutthole`

他们将收到一条错误响应，表明字段 `extra` 不被允许：

## 读者应该观察什么

- 文档与查询使用同一模型和Revision，但只有查询带任务指令；
- 向量经过L2归一化后，点积等于余弦相似度；
- Top 5来自NumPy全量精确排序，不是近似向量数据库；
- 分数和排名由程序计算，模型不评价自己的检索质量；
- 本检查点尚未冻结门控阈值，也未调用在线生成模型。

## 真实性声明

本检查点真实调用了本地Embedding模型；未调用在线生成模型或Codex Judge，也未产生RAG最终答案。
