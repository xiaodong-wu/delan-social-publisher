---
name: delan-social-publisher
description: 为德缆 DLFLEX / Delan Cable 从官网随机或指定选品，生成有依据的英文文案与四宫格图片，通过浏览器插件发布到 Facebook 主页 dlflexdelancable 并回写 Google 发布记录表。用于产品发布、素材预演、明确批次续跑或已发布帖子的表格补录；不含站内文章或 LinkedIn 发布。
---

# 德缆 Facebook 自动发布

每次运行只为一个德缆产品创建一条 Facebook 图文。

- 产品入口：`https://en.delancable.com/product`
- 唯一发布主页：`https://www.facebook.com/dlflexdelancable`
- 品牌：DLFLEX / Delan Cable（德缆）。以当前官网产品事实为准。
- 用户调用本技能要求发布，且未指定 `dry-run` / 仅预览时，视为授权通过预检后直接发布，无需再次询问常规确认。仅要求创建、修改或审阅技能不构成执行发布的授权。
- 不创建站内文章、LinkedIn 帖子、网站 API 请求或定时任务。不需要网站 API key。每次成功发布后必须回写指定 Google 表格；站内和 LinkedIn 两列填写“不适用”，详见 [references/reporting.md](references/reporting.md)。

## 运行步骤

### 1. 预检

阅读 [references/publishing.md](references/publishing.md)。Facebook 内容发布统一使用当前会话提供的浏览器插件工具（如 `mcp__cua_repl`），通过 Chrome 扩展连接操作已登录的浏览器会话，按工具返回文档进行身份检查、填写、上传、提交及公开结果核验。插件不可用或未连接时停止并报告所需操作，不改用发布 API、社媒连接器或独立浏览器自动化会话。Google 表格读取与回写继续使用原有 Sheets 连接器。

Live 运行在生成图片前打开指定主页，核实主页 URL、可见品牌、当前发布身份与创建帖子权限。主页数字 ID 未预设；若平台重定向到数字 ID，必须通过当前页面证据确认与 `dlflexdelancable` 对应并记录，不得借用其他品牌 ID。允许一次明确的主页身份切换及其确认。遇到登录、MFA、CAPTCHA、身份歧义或权限不足立即停止。

确认输出目录和图像生成工具可用。Live 运行同时读取 [references/reporting.md](references/reporting.md)，检查表格访问与五列表头。`dry-run` 不要求 Facebook 登录，不打开发布编辑器，不执行提交或表格写入；其余取证、文案和图片检查相同。图像生成前加载已安装的 `imagegen` 技能。

### 2. 检查历史，再选择和核实产品

阅读 [references/product-selection.md](references/product-selection.md)。每次先按 [references/history.md](references/history.md) 合并本地批次和实时 Google 表格，生成历史快照；无法关联产品的旧帖先打开核对。排除已发布及任何已提交但结果未定的产品，在剩余产品中随机抽取。全部已发布时停止，不自动循环复发。

历史快照通过后运行：

```bash
python3 scripts/scrape_product.py --output-root /absolute/path/to/campaign-runs \
  --history /absolute/path/to/history.json
# 指定产品或仅预览时按需追加：
# --product-url https://en.delancable.com/product/PRODUCT_ID
# --mode dry-run
```

脚本遍历所有目录分页，按规范产品 URL 去重并排除历史后随机抽取，最多审查 10 个未发布候选。历史排除不占事实审查预算。指定产品也检查历史且不可替换。所有运行文件保存在技能目录之外；同一账号持续使用相同输出根目录。`dry-run` 可只检查本地历史，但要说明覆盖范围，不能据此声称线上未发布。

使用返回的 `manifest.json`、`product.json`、`source/page.html` 和 `source/hero.*`。读取原始产品正文，并用 `view_image` 查看主图；不要只信脚本筛选结果。确认标题、正文、线芯结构、护套和可选配置无冲突。填写脚本创建的 `evidence/product-review.json`：将 `status` 设为 `approved`，填写 `reviewed_at`、`notes` 和 `usable_fact_ids`，保留空的 `conflicts` 列表；不得把有冲突的候选改成通过。

随机候选在任何提交前发现产品事实或源图问题时，可执行：

```bash
python3 scripts/scrape_product.py --retry-from MANIFEST --reason '具体的产品证据问题'
```

沿用同一选择台账及 10 个候选上限。不能因工具、网络、登录、生成或草稿格式错误换产品。任何提交开始后永久禁止换产品。普通新运行重新选品；只有用户指定批次或明确要求继续刚刚失败的批次时才续跑。

### 3. 文案与图片

阅读 [references/content-spec.md](references/content-spec.md)。

1. 写 `facebook.txt`：80–150 个英文词，保留四行 emoji 功能介绍、短收益段落、B2B 询盘 CTA、8–12 个相关标签的原有格式，仅移除原产品链接行。社媒正文不包含任何网站链接、www 地址或裸域名，也不添加链接预览卡片；官网产品 URL 仍保留在本地产品记录、历史去重和交付报告中。先读历史快照中最近最多五篇正文，在原格式内围绕本产品选型问题调整事实顺序、措辞、收益解释和 CTA，不只替换型号或同义词。
2. 使用产品类型、结构、用途中的已核实词语自然表达，不套用轮胎汽配词汇；无需生成站内 SEO 文章或文章关键词密度计划。
3. 填写 `evidence/copy-review.json`，将每个事实声明关联到事实 ID 或标题，检查数字和可选条件，并记录 `angle`、`recent_posts_reviewed` 和 `distinct_from_recent`。示例见内容规范。
4. 以查看过的主图为身份参考，用 `imagegen` 生成一张 1:1 四宫格社媒图；不生成封面或文章配图。保持线芯数量、配色、屏蔽、护套、端部结构和可见型号一致。不得凭空生成接头、认证标志或应用场景。
5. 检查生成图并填写 `evidence/image-review.json`。每张图最多初次生成 + 两次定向修正 + 一次保留原产品的背景/布局回退；重大结构错误仍存在就停止。
6. 把生成结果复制进本次运行目录，再执行优化。此脚本只负责必要的格式转换、裁剪、压缩和元数据移除；所有视觉内容生成与修正仍使用 `imagegen`。

```bash
python3 scripts/optimize_image.py GENERATED_IMAGE RUN_DIR/social.webp --kind social \
  --transport-jpeg RUN_DIR/social-upload.jpg
```

保留 `social.webp` 为正式素材；浏览器仅上传临时的 `social-upload.jpg`。两者均为正方形，最小 960×960、最大 1600×1600，不超过 750 KiB。像素重建清理 EXIF、XMP、ICC、注释及附加元数据，并检查两种最终容器；生成原图只归档，不直接上传。人工检查压缩成品未裁掉线缆端部或四宫格内容。

### 4. 验证、提交与结果核对

```bash
python3 scripts/validate_campaign.py MANIFEST
```

必须先通过整批验证；脚本会将各文件哈希写入 `evidence/campaign-validation.json`。验证通过不代表人工事实或视觉判断自动成立。`dry-run` 到此返回“预演通过，未发布”。

Live 运行按 [references/publishing.md](references/publishing.md) 核实编辑器身份、精确文案和上传预览，保存 `evidence/preflight.json`。**可选 AI 标签默认关闭，不因使用 imagegen 自动开启**；平台明确要求或用户明确要求时记录依据，不承诺平台不会自动标记。

最终点击发布前按历史规范刷新表格与本地记录，写 `evidence/history-preflight.json`。提交脚本在共享输出根目录加锁，再查同产品占用和重复文案，然后记录永久提交标记：

```bash
python3 scripts/update_manifest.py MANIFEST --status pending --submission-started
```

标记写入成功后仅点击一次发布。到主页时间线或已发布内容列表核对作者、文案、产品身份和图片，确认正文没有网站链接或链接预览卡片，打开公开永久链接，保存截图及 `evidence/facebook-publication.json`，再记录：

```bash
python3 scripts/update_manifest.py MANIFEST --status published --url PUBLIC_POST_URL \
  --evidence RUN_DIR/evidence/facebook-publication.json
```

结果不确定时记录 `uncertain`，先核对平台状态；没有确证帖子不存在就不可重发。详见发布规范的一次有界重试。已发布批次不可降级或重复发布。

### 5. 回写表格并完成核验

按 [references/reporting.md](references/reporting.md) 把本次记录写入 `social-auto-upload` 的 `工作表1`。用 Facebook 永久链接去重，写入后回读核对五列值和唯一性，保存真实连接器结果并执行：

```bash
python3 scripts/record_reporting.py MANIFEST --status reported \
  --evidence RUN_DIR/evidence/google-sheet-verification.json
python3 scripts/validate_completion.py MANIFEST
```

只有最终守卫输出 `complete` 才算完成。表格回写失败时保留 Facebook `published`，报告表格状态并只补录，不重发帖子。补录旧批次直接从本节开始。验证完成后可删除临时 JPEG，保留 WebP、哈希记录和证据；未完成时保留 JPEG 以便安全续跑。

## 交付

在本次运行目录写 `report.md`，并返回简短中文发布清单：产品名和官网链接、Facebook 状态和永久链接、Google 表格回写状态与行号/链接、尝试及跳过的候选数与原因、素材目录和台账链接。明确区分 `dry-run`、`blocked`、`failed`、`uncertain`、`reporting_pending` 和 `complete`。没有已验证的公开链接时不得宣称发布成功；回写未验证时不得宣称整个流程完成。

## 脚本与依赖

报告另列历史排除数量、文案切入点、实际 AI 标签状态及正式 WebP/上传 JPEG 的元数据检查结果。修改技能本身不触发发帖，不修改既有帖子。

脚本路径均相对本技能目录。Python 3.9+；图片处理需要 Pillow，其余仅用标准库。所有脚本只读官网或处理本地文件；实际 Facebook 发布通过浏览器插件操作已登录的浏览器完成。

```bash
python3 scripts/update_manifest.py MANIFEST --status blocked --error '具体阻塞原因'
python3 scripts/update_manifest.py MANIFEST --status uncertain --error '已点击提交，结果尚未核实'
```
