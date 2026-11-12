# Facebook 发布与完成证据

唯一目标：`https://www.facebook.com/dlflexdelancable`。

## 身份与预检

优先查询当前可用连接器；只有能完整验证主页身份、媒体预览、提交结果和永久链接的路线才适用。否则使用当前受支持浏览器控制和已登录的 Chrome。`cua_repl` 应先按工具文档选择浏览器或标签，再读取返回的 API 文档；不得臆造旧接口。浏览器不可用或未登录时停止，不能改用新会话假装已经检查账号。

Live 生成前及最终提交前都检查指定主页的 URL、可见 DLFLEX / Delan Cable 身份、当前发帖身份、创建帖子入口。数字 ID 只能来自本次从精确用户名主页出发的已验证导航，不得预填参考技能的主页 ID。通用首页或同名主页不算匹配。

在已登录会话中，若指定主页明确显示切换为此主页的按钮，允许点击一次，并在明确写着同一目标的确认对话框内确认一次。若无需确认则直接验证。重新打开精确目标 URL；仍要求切换、出现账号选择器、密码、MFA、CAPTCHA、checkpoint 或权限问题就停止。不得反复切换或选择其他账号。

最终提交前保存 `evidence/preflight.json`，所有字段来自本次观察：

```json
{"target_url":"https://www.facebook.com/dlflexdelancable","checked_at":"ISO-8601 timestamp","identity_confirmed":true,"can_create_post":true,"active_identity":"实际观察到的主页身份","observed_page_id":"仅在可验证时填写","evidence_file":"evidence/facebook-preflight.png"}
```

截图路径相对运行目录。连接器路线可保存等价的响应证据文件。提交时预检记录须在过去 30 分钟以内。此记录不应包含凭据或完整会话数据。

## AI 标签与上传文件

可选“AI 标签”默认关闭；如编辑器继承此前开启状态，应关闭并核对，不因使用 imagegen 主动开启。预检 JSON 增加 `ai_label: {"value":"off","reason":"实际观察和关闭理由"}`。没有该选项时记录 `value: "unavailable"` 与实际情况。

平台明确强制披露或用户明确要求开启时，记录 `value: "on"`、`basis: "platform_required"` 或 `"user_requested"`、`reason` 和 `evidence`（实际平台截图路径或用户原话）。不隐藏强制披露、不承诺平台不会自动打标；无法判断是否强制时停止说明。

只上传本次优化和校验后的 `social-upload.jpg`；正式 WebP 同时归档。元数据清理独立于可选标签设置，必须校验实际上传文件。

## 提交

1. 读取并通过 `validate_campaign.py`；确认文件未被改动。
2. 在目标主页打开创建帖子，粘贴 `facebook.txt` 全文并上传 `social-upload.jpg`。WebP 是归档素材，JPEG 是浏览器传输衍生件。
3. 检查预览的身份、完整文案、图片四宫格、无残留其他草稿；新批次正文不得有网站链接或链接预览卡片。
4. 按 [history.md](history.md) 刷新历史预检，再运行 `update_manifest.py MANIFEST --status pending --submission-started`。脚本在共享根目录锁下重查同产品占用，只有标记成功才点击最终发布一次。
5. 等待平台结果，打开目标主页时间线或 Meta 已发布内容列表，检查作者、产品身份、全文、图片和时间，确认无网站链接及链接预览卡片。以文案中的产品名/规格和图片对照本批次 manifest、已审阅产品事实及素材，不能靠正文链接判断产品。取得并打开公开帖子永久链接；仅有 toast、编辑器关闭、草稿或排期成功都不算已发布。
6. 写 `evidence/facebook-publication.json` 后记录 `published`，运行 `validate_completion.py`。不要在此流程发布站内内容或其他社交渠道。

发布证据格式（截图及文件均相对运行目录）：

```json
{"target_url":"https://www.facebook.com/dlflexdelancable","post_url":"实际公开永久链接","verified_at":"ISO-8601 timestamp","author_matches":true,"text_matches":true,"product_matches":true,"no_website_links":true,"image_matches":true,"evidence_file":"evidence/facebook-published.png","notes":"记录作者、正文产品名/规格和图片与本批次的对应关系，并确认正文无网站链接及链接预览卡片"}
```

以上格式适用于新建 version 3 批次。`no_website_links` 只有观察到公开正文和预览确实无网站链接时才设为 true。version 1/2 已提交旧批次继续要求原 `product_link_matches: true` 证据；不修改旧文案、manifest 版本或冻结哈希来适配新规则。

URL 可为该用户名下 `/posts/...`、已核实同主页数字 ID 下 `/posts/...`，或含 `story_fbid` 和 `id` 的 `permalink.php` / `story.php`。如果平台给出不同形式，打开并取得可核对的永久链接；不得保存主页、登录页、编辑器、分享跳转或随意改写 URL。脚本检查 URL 形态，实际作者对应关系必须由当前平台证据确认。

## 不确定结果与续跑

- 已点击后没有确定结果：记录 `uncertain`，保留素材及永久提交历史，不能换产品或新建台账掩盖原提交。
- 先查看主页时间线、已发布内容、草稿、排期、相关时间范围与通知。找到匹配帖子就记录成功，不重复发布。
- 仅当当前证据明确证明第一次没有发布、没有等待审核或排期任务时，允许一次同批次重试。保存 `evidence/reconciliation.json`：`target_url`、`checked_at`、`confirmed_absent: true`、`no_pending_submission: true`、非空 `notes`、`evidence_file`；然后用 `--submission-started --reconciliation FILE` 记录第二次提交。不能仅因暂时看不到帖子就断言未发布；仍不确定则停止。
- 不自动撤回成功帖子，不降级已发布状态；已发布批次重跑仅补核验/报告。用户明确要求恢复某批次时重新预检，但跳过已发布结果。
- `dry-run` 永远不能记录提交或发布成功；需要正式发布时新建 live 批次，重新预检。
- 完成守卫同时检查正式素材、提交时的验证哈希、永久提交历史、公开证据、目标主页及 Google 表格回写证据。临时 JPEG 在 `complete` 后可删除，其他证据须保留。

核实 Facebook 发布后必须按 [reporting.md](reporting.md) 回写指定 Google 表格，以 Facebook 永久链接去重，站内和 LinkedIn 两列填“不适用”。回写并回读成功前，不得报告整体完成；回写失败不能导致重发。
