# 使用示例

需要演示、验证输入格式或检查异常降级时读取本文件。完整字段定义见 [contracts.md](contracts.md)。

## 多来源数值冲突

运行：

```bash
python scripts/audit_evidence.py examples/conflict.json --pretty
```

预期：保留 91% 和 84% 两条不同来源证据；对应主张标记为 `contested`，`conflicts` 引用双方证据，并提示核验数据集、统计口径、版本和时间。

## 无证据拒答

运行：

```bash
python scripts/audit_evidence.py examples/no-evidence.json --pretty
```

预期：返回 `status: refused`，不生成已验证主张，并在 `gaps` 中说明缺少可核验证据。

## 论文与代码联合核验

运行：

```bash
python scripts/audit_evidence.py examples/paper-code.json --pretty
```

预期：同时保留论文 DOI 与代码文件行号或符号；只对证据直接覆盖的主张给出支持关系，不根据论文描述推断代码已经实现未展示的功能。
