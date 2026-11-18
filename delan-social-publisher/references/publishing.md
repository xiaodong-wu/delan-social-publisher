# Facebook 发布与完成证据

唯一目标：`https://www.facebook.com/dlflexdelancable`。

## 身份与预检

Facebook 页面操作统一通过浏览器插件（如 `mcp__cua_repl`）连接已登录的 Chrome。按插件当前文档定位浏览器。需要从清单选择时，匹配 Chrome 的 `type=extension`，使用本次返回的浏览器和标签标识。复用此会话中精确指向目标主页的标签。只有其他品牌、个人首页、历史帖子或已有草稿时，在同一扩展会话新开目标主页，保留原标签。扩展已连接但标签列表为空时也可直接新开。多个配置文件无法区分时，请用户指出发布用的 Chrome 配置文件。

插件未安装、未连接、浏览器不可用或未登录时停止，报告需要用户完成的连接或登录操作；不回退到 Facebook API、社媒发布连接器或其他发布方式。Google 表格仍按 [reporting.md](reporting.md) 使用 Sheets 连接器；官网取证和本地素材脚本保持原流程。

先读当前 URL 和主页标题，再看谁正在操作。“管理公共主页”标题可能与“以其他品牌的身份评论”“切换到 Dlflex Delan Cable”同时出现。此时仍需切换。生成图片前确认当前身份属于德缆且主页内容区可创建帖子。数字 ID 仅取自本次已核实的目标主页链接或跳转。顶部广告中心可能仍属于另一个账号，单独出现的数字不能用作德缆主页 ID。

在已登录会话中，若指定主页明确显示切换为此主页的按钮，允许点击一次，并在明确写着同一目标的确认对话框内确认一次。若无需确认则直接验证。重新打开精确目标 URL；仍要求切换、出现账号选择器、密码、MFA、CAPTCHA、checkpoint 或权限问题就停止。不得反复切换或选择其他账号。

打开编辑器后，从当前发帖对话框的作者区域读取显示名称 `Dlflex Delan Cable` 或实际显示的完整账号 `@dlflexdelancable`，原样写入 `active_identity`。提交脚本容许大小写、显示空白和账号前的 @ 差异。仅见主页标题、历史帖作者或评论身份时，不足以确认草稿作者。若编辑器身份与目标冲突，保留草稿状态，停止提交。

最终提交前保存 `evidence/preflight.json`，所有字段来自本次观察：

```json
{"target_url":"https://www.facebook.com/dlflexdelancable","checked_at":"ISO-8601 timestamp","identity_confirmed":true,"can_create_post":true,"active_identity":"实际观察到的主页身份","observed_page_id":"仅在可验证时填写","evidence_file":"evidence/facebook-preflight.png"}
```

截图路径相对运行目录，保存浏览器插件取得的实际页面截图；可附当前页面的 DOM 或可访问性树辅助核对。提交时预检记录须在过去 30 分钟以内。此记录不应包含凭据或完整会话数据。

## AI 标签与上传文件

可选“AI 标签”默认关闭；如编辑器继承此前开启状态，应关闭并核对，不因使用 imagegen 主动开启。预检 JSON 增加 `ai_label: {"value":"off","reason":"实际观察和关闭理由"}`。没有该选项时记录 `value: "unavailable"` 与实际情况。

平台明确强制披露或用户明确要求开启时，记录 `value: "on"`、`basis: "platform_required"` 或 `"user_requested"`、`reason` 和 `evidence`（实际平台截图路径或用户原话）。不隐藏强制披露、不承诺平台不会自动打标；无法判断是否强制时停止说明。

只上传本次优化和校验后的 `social-upload.jpg`。按插件当前的文件上传文档，先监听文件选择事件，再点击发帖编辑器内实际触发选择器的“照片/视频”或“添加照片”控件。若先出现上传面板，就在面板内定位触发器。选择器超时先检查弹窗、附件和上传状态，按插件上传故障说明恢复。已有本次附件时等待上传完成，不重复附图。核对只有一张预期四宫格，且前进或发布按钮已启用。

## 提交

1. 读取并通过 `validate_campaign.py`；确认文件未被改动。
2. 在主页发帖区域定位“分享新鲜事 / What's on your mind?”等创建入口。对话框就绪后，在框内按当前可见角色和名称定位正文输入区。勿选时间线评论框、广告、快拍或 Reels。每次切换标签、打开弹窗或进入下一页后，读取新的可访问性树。增量树缺少上下文时再取完整树；同名控件先缩小到当前区域，仍有歧义时检查截图。不要复用上一步的元素编号或坐标。
3. 确认空白或本批次草稿后粘贴 `facebook.txt`。已有其他草稿时保留原稿。回读编辑器全文核对功能行、段落和标签（可忽略界面渲染产生的空白差异），并按上节核对图片和 AI 标签；正文不得有网站链接或预览卡。若有“下一页 / Next”，进入帖子设置后核对公开、立即发布及唯一目标主页。若编辑器直接提供最终发布按钮，就在该页做相同预检。
4. 按 [history.md](history.md) 刷新历史预检，再运行 `update_manifest.py MANIFEST --status pending --submission-started`。脚本在共享根目录锁下重查同产品占用，只有标记成功才点击最终发布一次。
5. 点击后若显示“发布中”、跳出可跳过的附加按钮建议，或暂时重新显示“发帖”，保持已提交状态。跳过可选建议，查看时间线或已发布内容；不要再次点击发布。用德缆作者、当前产品规格和正文定位本帖，再打开**同一帖子**的时间链接。在永久链接内展开全文，核对公开受众、作者、时间、全文和四宫格。仅在本帖正文及附件内检查网站链接和预览卡，区分 Facebook 自动生成的标签链接、作者链接和图片链接。仅有成功提示、编辑器关闭、草稿或排期均不足以登记。
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
