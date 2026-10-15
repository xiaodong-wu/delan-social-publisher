---
name: delan-social-publisher
description: 为德缆 DLFLEX / Delan Cable 从 https://en.delancable.com/product 随机或指定选择一个产品，生成有官网依据的英文 B2B 文案与无元数据四宫格图片，并发布到 Facebook 主页 dlflexdelancable。用于德缆产品社媒发布、素材预演和明确指定批次的续跑；仅含 Facebook，不含站内文章或 LinkedIn。
---

# 德缆 Facebook 自动发布

每次运行只为一个德缆产品创建一条 Facebook 图文。

- 产品入口：`https://en.delancable.com/product`
- 唯一发布主页：`https://www.facebook.com/dlflexdelancable`
- 品牌：DLFLEX / Delan Cable（德缆）。以当前官网产品事实为准。
- 用户调用本技能要求发布，且未指定 `dry-run` / 仅预览时，视为授权通过预检后直接发布，无需再次询问常规确认。仅要求创建、修改或审阅技能不构成执行发布的授权。
- 不创建站内文章、LinkedIn 帖子、网站 API 请求或定时任务。不需要网站 API key。不沿用参考技能要求三渠道链接的 Google Sheet；本技能使用本地 manifest 和发布清单。只有用户另行指定表格及列结构时才增加表格回写。

## 运行步骤

### 1. 预检

阅读 [references/publishing.md](references/publishing.md)。先查询可用发布连接器；没有合适连接器时，使用当前受支持的浏览器工具及其返回文档，优先复用已登录的 Chrome 会话。不要导入旧版浏览器运行时。

Live 运行在生成图片前打开指定主页，核实主页 URL、可见品牌、当前发布身份与创建帖子权限。主页数字 ID 未预设；若平台重定向到数字 ID，必须通过当前页面证据确认与 `dlflexdelancable` 对应并记录，不得借用其他品牌 ID。允许一次明确的主页身份切换及其确认。遇到登录、MFA、CAPTCHA、身份歧义或权限不足立即停止。

确认输出目录和图像生成工具可用。`dry-run` 不要求 Facebook 登录，不打开发布编辑器，不执行提交；其余取证、文案和图片检查相同。图像生成前加载已安装的 `imagegen` 技能。

### 2. 选择和核实产品

阅读 [references/product-selection.md](references/product-selection.md)，运行：

```bash
python3 scripts/scrape_product.py --output-root /absolute/path/to/campaign-runs
# 指定产品或仅预览时按需追加：
# --product-url https://en.delancable.com/product/PRODUCT_ID
# --mode dry-run
```

脚本遍历所有目录分页，按 URL 去重后随机抽取，最多尝试 10 个不同产品。指定产品默认不可替换。所有文件保存在技能目录之外。

使用返回的 `manifest.json`、`product.json`、`source/page.html` 和 `source/hero.*`。读取原始产品正文，并用 `view_image` 查看主图；不要只信脚本筛选结果。确认标题、正文、线芯结构、护套和可选配置无冲突。填写脚本创建的 `evidence/product-review.json`：将 `status` 设为 `approved`，填写 `reviewed_at`、`notes` 和 `usable_fact_ids`，保留空的 `conflicts` 列表；不得把有冲突的候选改成通过。

随机候选在任何提交前发现产品事实或源图问题时，可执行：

```bash
python3 scripts/scrape_product.py --retry-from MANIFEST --reason '具体的产品证据问题'
```

沿用同一选择台账及 10 个候选上限。不能因工具、网络、登录、生成或草稿格式错误换产品。任何提交开始后永久禁止换产品。普通新运行重新选品；只有用户指定批次或明确要求继续刚刚失败的批次时才续跑。

### 3. 文案与图片

阅读 [references/content-spec.md](references/content-spec.md)。

1. 根据已批准的产品证据写 `facebook.txt`：80–150 个英文词，四行 emoji 功能介绍、短收益段落、B2B 询盘 CTA、独占一行的完整产品链接、8–12 个相关标签。
2. 使用产品类型、结构、用途中的已核实词语自然表达，不套用轮胎汽配词汇；无需生成站内 SEO 文章或文章关键词密度计划。
3. 填写 `evidence/copy-review.json`，将每个产品事实声明关联到 `product.json` 的事实 ID 或标题，并检查所有数字、条件与可选项。示例见内容规范。
4. 以查看过的主图为身份参考，用 `imagegen` 生成一张 1:1 四宫格社媒图；不生成封面或文章配图。保持线芯数量、配色、屏蔽、护套、端部结构和可见型号一致。不得凭空生成接头、认证标志或应用场景。
5. 检查生成图并填写 `evidence/image-review.json`。每张图最多初次生成 + 两次定向修正 + 一次保留原产品的背景/布局回退；重大结构错误仍存在就停止。
6. 把生成结果复制进本次运行目录，再执行优化。此脚本只负责必要的格式转换、裁剪、压缩和元数据移除；所有视觉内容生成与修正仍使用 `imagegen`。

```bash
python3 scripts/optimize_image.py GENERATED_IMAGE RUN_DIR/social.webp --kind social \
  --transport-jpeg RUN_DIR/social-upload.jpg
```

保留 `social.webp` 为正式素材；浏览器仅上传临时的 `social-upload.jpg`。两者均为正方形，最小 960×960、最大 1600×1600，不超过 750 KiB，无 EXIF/XMP/ICC 元数据。人工检查压缩成品未裁掉线缆端部或四宫格内容。

### 4. 验证、提交与结果核对

```bash
python3 scripts/validate_campaign.py MANIFEST
```

必须先通过整批验证；脚本会将各文件哈希写入 `evidence/campaign-validation.json`。验证通过不代表人工事实或视觉判断自动成立。`dry-run` 到此返回“预演通过，未发布”。

Live 运行按 [references/publishing.md](references/publishing.md) 核实编辑器身份、精确文案和上传预览，保存 `evidence/preflight.json`。最终点击发布前记录永久提交标记：

```bash
python3 scripts/update_manifest.py MANIFEST --status pending --submission-started
```

标记写入成功后仅点击一次发布。到主页时间线或已发布内容列表核对作者、文案、产品链接和图片，打开公开永久链接，保存截图及 `evidence/facebook-publication.json`，再记录：

```bash
python3 scripts/update_manifest.py MANIFEST --status published --url PUBLIC_POST_URL \
  --evidence RUN_DIR/evidence/facebook-publication.json
python3 scripts/validate_completion.py MANIFEST
```

只有最终守卫输出 `complete` 才算完成。结果不确定时记录 `uncertain`，先核对平台状态；没有确证帖子不存在就不可重发。详见发布规范的一次有界重试。验证完成后可删除临时 JPEG，保留 WebP、哈希记录和证据；未完成时保留 JPEG 以便安全续跑。已发布批次不可降级或重复发布。

## 交付

在本次运行目录写 `report.md`，并返回简短中文发布清单：产品名和官网链接、Facebook 状态和永久链接、尝试及跳过的候选数与原因、素材目录和台账链接。明确区分 `dry-run`、`blocked`、`failed`、`uncertain` 和 `complete`。没有已验证的公开链接时不得宣称发布成功。

## 脚本与依赖

脚本路径均相对本技能目录。Python 3.9+；图片处理需要 Pillow，其余仅用标准库。所有脚本只读官网或处理本地文件；实际发布由受支持连接器或浏览器完成。

```bash
python3 scripts/update_manifest.py MANIFEST --status blocked --error '具体阻塞原因'
python3 scripts/update_manifest.py MANIFEST --status uncertain --error '已点击提交，结果尚未核实'
```
