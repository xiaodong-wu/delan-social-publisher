# Google 表格回写

每次已授权的 live 运行，在 Facebook 帖子发布并核实永久链接后，立即写入一条发布记录。回写属于本技能流程，无需额外确认。写入并回读验证后才可报告 `complete`。`dry-run` 不写表；Facebook 尚未确认成功时不创建记录。

## 固定目标和五列

- 表格：[social-auto-upload](https://docs.google.com/spreadsheets/d/18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw/edit?gid=0)
- spreadsheet ID：`18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw`
- 工作表：`工作表1`，sheetId `0`；每次先读取最新元数据和表头。
- A1:E1 必须是：`域名`、`发布时间`、`发布的站内链接`、`Facebook链接`、`LinkedIn链接`。
- 五列值：`en.delancable.com`、北京时间 `YYYY-MM-DD HH:mm:ss`、`不适用`、已核实的 Facebook 永久链接、`不适用`。
- 时间取本批次 `facebook-publication.json` 的 `verified_at` 转为 Asia/Shanghai，表示发布核验时间；补录保留原时间，不改为补录时间。官网产品详情页不是本次新发文章，不填入站内发布列。

加载可用的 `google-drive:google-sheets` 技能，使用受支持的 Google Sheets 连接器。表名、工作表或表头不匹配时停止回写，不新建替代表格，不改表结构。

## 写入和去重

1. 生成五列值：`python3 scripts/record_reporting.py MANIFEST --plan`。脚本仅生成本地计划，不写远程表格。
2. 使用 `search_spreadsheet_rows` 在当前行数边界内的 A:E 搜索精确 Facebook 永久链接。表格当前为 1000 行，搜索 A1:E1000 共 5000 个单元格；每次按实时 metadata 的 rowCount 调整，不能超过连接器的 50000 单元格上限。
3. 如果已存在且五列完全一致，直接回读验证并记录；不要新增。如果同一帖子链接出现多行或任一值冲突，记录 reporting `blocked`，不要覆盖。
4. 无匹配时，检查表尾及待写行的 CellData，确认值、公式、验证和格式。只在当前数据尾部追加一行五个字符串，遵循 Sheets 技能的原生单元格规则；保留现有其他行和列结构。若并发写入导致目标行被占用，刷新后重新选择空行。
5. 写入结果不明时，先按同一永久链接重新搜索，再决定是否需要一次有界重试，禁止盲目重复写入。表格失败不得触发 Facebook 重发。
6. 写入后用 `get_spreadsheet_cells` 回读 `A1:E1` 和实际写入的 `A行号:E行号`，字段至少包含 `userEnteredValue,formattedValue`。再运行步骤 2 的精确链接搜索，必须只有一个匹配行。两个返回值中的 `structuredContent` 原样保存到 `evidence/google-sheet-verification.json` 的 `readback` 和 `search` 字段，并加上真实 `verified_at` 和 `row_number`：

```json
{
  "verified_at": "实际回读完成时间，带时区的 ISO 8601",
  "row_number": 59,
  "readback": {"说明": "get_spreadsheet_cells 的完整 structuredContent，包含表头及目标行"},
  "search": {"说明": "search_spreadsheet_rows 的完整 structuredContent"}
}
```

示例行号不可直接沿用；不要编造工具返回。若连接器返回结构变化或表格超出单次有界搜索上限，保留实际结果并报告校验限制，不伪造成功。

7. 验证写入证据、记录回写状态并运行完成守卫：

```bash
python3 scripts/record_reporting.py MANIFEST --status reported \
  --evidence RUN_DIR/evidence/google-sheet-verification.json
python3 scripts/validate_completion.py MANIFEST
```

守卫核对固定表头、完整五列值、表格身份、唯一匹配及本地证据哈希。输出 `complete` 才算整个流程完成。确认 Google 渲染的目标行后保存截图。

回写失败：`python3 scripts/record_reporting.py MANIFEST --status blocked --error '具体原因'`，也支持 `failed` 和 `uncertain`。报告“Facebook 已发布，表格回写未完成”。只补录已发布批次时，直接使用原 manifest 和永久链接，从本节开始；不重新选品、不生成图片、不重复发帖。
