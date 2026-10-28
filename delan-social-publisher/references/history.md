# 选品前与提交前核对历史

同一账号所有运行复用相同 `campaign-runs` 根目录，新批次在其下建独立子目录。不要更换根目录规避历史。历史、原始表格返回和截图只留本地，不上传公开仓库。

## 生成历史快照

1. 按 Google Sheets 技能读取 reporting.md 指定表格的 metadata，再按当前 rowCount 有界读取 `工作表1` 的 A1:E行数。当前 1000 行共 5000 单元格。如果超过 50000，停止报告当前脚本不支持分块，不能只查前面部分。
2. 将两次完整 `structuredContent` 保存为本次 `sheet-source.json`，时间是真实读取时间，不通过更新旧文件时间伪装新读取：

```json
{
  "checked_at": "带时区的实际读取时间",
  "metadata": {"此处": "metadata 的完整 structuredContent"},
  "rows": {"此处": "get_spreadsheet_range 的完整 structuredContent"},
  "post_mappings": []
}
```

3. 运行合并脚本。它扫描根目录下所有 live manifest：已发布、结果不明及任何留下提交标记的产品均排除；即便表格回写失败也不能复发。未提交草稿、拒绝候选和 dry-run 不算已发布。损坏的 manifest 不会被静默忽略。

```bash
python3 scripts/publication_history.py --output-root /absolute/path/to/campaign-runs \
  --sheet-evidence /absolute/path/to/sheet-source.json \
  --output /absolute/path/to/history.json
```

4. 表格 C 列仍是“不适用”，不能当产品链接。脚本用 D 列帖子链接关联本地 manifest 的产品。`unresolved_posts` 非空时，打开列出的永久帖子核实作者和正文产品链接，保存正文和截图，在源文件 `post_mappings` 增加：

```json
{
  "post_url": "表格中的实际 Facebook 永久链接",
  "product_url": "正文里的 https://en.delancable.com/product/数字ID",
  "verified_at": "实际核验时间",
  "author_matches": true,
  "product_link_verified": true,
  "copy": "实际帖子的完整正文",
  "evidence_file": "相对 sheet-source.json 的截图或连接器证据路径"
}
```

无法读取、没有唯一产品链接、身份不明或映射矛盾时停止，不能猜型号。映射可复用已有证据，但每次表格读取必须新鲜。

5. 再运行合并脚本，必须输出 `ready`。在 30 分钟内传给 `scrape_product.py --history FILE`；脚本记录完整目录、历史排除列表、本次候选及历史快照。产品按官网数字 ID 比较，忽略追踪参数和尾斜杠；不同 ID 的同名产品分别保留。

没有未发布候选，或十次事实审查全部失败时报告 `blocked`，不自动循环已发布产品。指定已发布产品也阻塞；另行明确要求重发时再制定该次方案，本技能没有自动绕过去重的开关。

## 提交前再次检查

刷新 Sheet metadata 和 A:E，保存新源文件，再生成以下证据。`--exclude-manifest` 仅排除当前批次；重试时不能把自己误当另一个任务，其他批次标记必须保留。

```bash
python3 scripts/publication_history.py --output-root /absolute/path/to/campaign-runs \
  --sheet-evidence /absolute/path/to/fresh-sheet-source.json \
  --exclude-manifest /absolute/path/to/RUN/manifest.json \
  --output /absolute/path/to/RUN/evidence/history-preflight.json
```

提交脚本在共享根目录加锁，重读其他批次：同产品已发布或被另一提交占用即拒绝；同时检查重复/高度相似正文和预检 AI 标签状态。相似度只能发现近似复制，不能代替人工审阅。

锁只覆盖使用同一根目录的本机任务，不能锁住其他设备或人工发帖。如有外部发布者，提交前同时核对主页近期内容，发现新帖就更新映射后重新选品。提交后不换产品；结果不明先核对；表格失败只补录。

已发布旧批次仍可用原 manifest 核验和补表，不改旧文案、素材或哈希。旧版未提交草稿在提交前也必须补齐历史预检与 AI 标签状态。新版本的完成校验保留旧批次的原文案规则。
