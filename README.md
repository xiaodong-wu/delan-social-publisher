# 德缆 Facebook 自动发布技能

`delan-social-publisher` 是为 Codex 编写的德缆 DLFLEX / Delan Cable 产品发布技能：从官网随机或指定选取一个产品，整理有来源依据的英文 B2B 文案，生成四宫格图片，并发布到指定 Facebook 主页。

- 产品目录：[en.delancable.com/product](https://en.delancable.com/product)
- 发布主页：[dlflexdelancable](https://www.facebook.com/dlflexdelancable)
- 仅发布 Facebook，不包含站内文章或 LinkedIn。
- 支持 `dry-run`、候选筛选、同批次续跑、提交结果核对和防重复发布。

## 安装

下载 [技能 ZIP](delan-social-publisher.zip)，将其中的 `delan-social-publisher` 文件夹放入 Codex 的技能目录 `~/.codex/skills/`。保留 `SKILL.md`、`agents/`、`references/` 和 `scripts/` 的目录关系。

也可克隆仓库后复制同名子目录：

```bash
git clone https://github.com/xiaodong-wu/delan-social-publisher.git
```

本技能需要 Python 3.9+、Pillow，以及 Codex 中可用的 `imagegen` 技能和受支持的浏览器控制或发布连接器。脚本使用 Unix 文件锁，适用于 macOS/Linux。真实发布还需要目标 Facebook 主页的登录会话和发帖权限。仓库不包含账号、密钥、浏览器会话或发布记录。

```bash
python3 -m pip install Pillow
```

## 使用

在 Codex 中调用：

```text
使用 $delan-social-publisher 随机选择一个德缆官网产品，预检通过后直接发布到指定 Facebook 主页，并返回发布清单。
```

仅准备素材、验证而不发布：

```text
使用 $delan-social-publisher dry-run，随机选择一个产品，生成并验证 Facebook 文案和四宫格图片，不提交发布。
```

可在请求中提供 `https://en.delancable.com/product/<产品ID>` 指定产品。该技能不会自动创建定时任务。

完整流程、授权边界和错误处理见 [SKILL.md](delan-social-publisher/SKILL.md)。

## 内容与验证

- 英文正文 80–150 词，四行功能介绍、产品价值、询盘 CTA、产品链接和 8–12 个标签。
- 一张四宫格社媒图片，正式素材为无 EXIF/XMP/ICC 元数据的 WebP，浏览器上传使用临时 JPEG。
- 参数必须来自对应产品的官网证据，保留可选配置与测试条件；不能将认证徽标当作该型号已获认证的证明。
- 发布前验证身份、文案、图片和文件哈希；提交结果不确定时先核对平台状态，禁止猜测性重复提交。
- 本地 JSON 记录不代替实际平台验证；只有取得并核对公开帖子永久链接后才能报告完成。

2026-10-15 已完成官网 4 页、48 个唯一产品链接的抓取检查及 17 项离线回归测试。此次打包尚未执行真实图片生成或 Facebook 发帖。

运行离线测试：

```bash
python3 -m unittest discover -s delan-social-publisher/scripts -p 'test_*.py' -v
```

运行只读产品提取（不会发布，也不会生成营销图片）：

```bash
python3 delan-social-publisher/scripts/scrape_product.py \
  --mode dry-run --output-root ./campaign-runs
```

运行数据保存在技能目录之外，不纳入此仓库。
