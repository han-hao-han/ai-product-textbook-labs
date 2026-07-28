# FastAPI文档来源与第三方许可说明

本实验计划从以下官方来源获取FastAPI中文文档：

```text
Repository: https://github.com/fastapi/fastapi
Release: 0.136.3
Commit: 82064857539e6286522c347b4b11331b48dd2378
```

FastAPI项目根目录在该Commit下提供MIT许可证。

Copyright (c) 2018 Sebastián Ramírez

```text
The MIT License (MIT)

Copyright (c) 2018 Sebastián Ramírez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

本仓库不提交FastAPI官方ZIP、完整原始文档、`docs_src`源码副本、
`fastapi/openapi/docs.py`源码副本或完整清洗语料，只提交下载与处理代码、
固定来源配置、manifest及经人工检查的有限示例。

语料处理默认只展开 `docs_src/**`。固定中文页面
`docs/zh/docs/how-to/configure-swagger-ui.md` 还会精确展开同一Commit中的
`fastapi/openapi/docs.py` 第9至24行；该例外及出现次数记录在来源配置和文档
manifest中，并受同一MIT许可证约束。

FastAPI名称仅用于描述文档来源和实验对象，不表示FastAPI项目或其作者对本教材提供官方认证、合作或背书。

## Qwen3-Embedding模型

检查点2使用以下官方模型仓库和固定Revision：

```text
Model: Qwen/Qwen3-Embedding-0.6B
Official repository: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
Revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
License: Apache-2.0
```

模型仓库在该Revision的元数据中声明Apache-2.0许可证。本实验仓库只保存固定模型
配置、下载与核验逻辑，不提交或重新分发模型权重。读者运行准备脚本后，模型文件
保存在Hugging Face共享缓存；运行记录只保存必要文件的大小、SHA-256和核验结论，
不保存本地缓存绝对路径。

模型的使用仍须遵守其官方仓库说明和Apache License 2.0：

```text
https://www.apache.org/licenses/LICENSE-2.0
```
