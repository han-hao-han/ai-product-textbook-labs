# XFUND本地数据说明

## 来源

- 官方仓库：<https://github.com/doc-analysis/XFUND>
- 官方发布：<https://github.com/doc-analysis/XFUND/releases/tag/v1.0>
- 许可证：CC BY-NC-SA 4.0
- 本项目用途：非商业教学

## 官方中文资产

| 文件 | 字节数 | 用途 |
|---|---:|---|
| `zh.train.json` | 4,674,754 | 训练分组标注 |
| `zh.train.zip` | 206,389,536 | 训练分组图片 |
| `zh.val.json` | 1,711,142 | 发布版验证分组标注 |
| `zh.val.zip` | 69,217,820 | 发布版验证分组图片 |

论文把后50张表单描述为测试集；官方发布文件和官方加载器使用`val`命名。本工程沿用发布文件名，并在读者说明中保留该差异。

## 本地目录

运行下载脚本后预计生成：

```text
data/raw/xfund_v1.0/
├─ zh.train.json
├─ zh.train.zip
├─ zh.train/
├─ zh.val.json
├─ zh.val.zip
├─ zh.val/
└─ download_manifest.json
```

候选查看工具生成：

```text
data/local/
├─ candidate_manifest.json
├─ candidate_gallery.html
├─ validation_candidate_manifest.json
└─ validation_candidate_gallery.html
```

这些文件只保存在本地，不上传仓库。

## 参考结果转换规则

只转换同时满足以下条件的实体关系：

```text
question实体
→ 显式linking关系
→ answer实体
```

不转换：

- `header`；
- `other`；
- 未关联实体；
- 仅凭空间距离推断的关系；
- 关系指向不存在实体的异常记录。

转换结果是“人工标注参考结果”，不是模型输出。

## 隐私和许可复核

XFUND论文说明表单内容由人工填写的合成信息构成，但主样本、观察样本、验证样本和仓库示例仍需逐张检查。身份证号码是硬性排除项；姓名允许出现；电话、地址、账号、签名、机构标识及其他信号只记录和人工复核，不参与候选排序。
