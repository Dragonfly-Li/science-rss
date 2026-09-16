# Science RSS v2

面向科研阅读的个人 RSS 聚合器。它抓取 15 个中英文科学资讯源，生成每个来源的独立 RSS、总聚合 RSS，以及软物质、活性物质和凝聚态物理三个主题精选源。

## v2 新增内容

- `softmatter.xml`：软物质精选
- `active_matter.xml`：活性物质精选
- `condensed_matter.xml`：凝聚态物理精选
- `all_ai.xml`：全部精选文章的 AI 中文摘要，推荐订阅
- `softmatter_ai.xml`、`active_matter_ai.xml`、`condensed_matter_ai.xml`：各主题的 AI 摘要源
- 标题与摘要采用不同权重，标题命中优先级更高
- 支持中英文关键词、排除词和全局噪声词
- `health.json`：每个来源的状态、条目数、耗时和错误信息
- 来源失败时读取上次成功缓存，不让单站故障拖垮整体
- 动态网站在普通抓取失败时按需启用无头浏览器兜底
- AI 摘要约 300 个汉字，依次说明研究动机、方法、主要结论和意义
- 摘要按文章链接缓存，已经处理过的文章不会重复付费
- 新版首页集中显示订阅入口和抓取健康状况
- 离线单元测试，以及部署前自动测试

## 最快部署方式

1. 在 GitHub 新建仓库，例如 `science-rss`。
2. 上传本项目内的全部文件和隐藏目录 `.github`。
3. 打开仓库的 **Settings → Pages**，将 Source 设为 **GitHub Actions**。
4. 打开 **Actions → Build and publish RSS → Run workflow**。

### 配置 AI 摘要

在 GitHub 仓库打开 **Settings → Secrets and variables → Actions**：

1. 在 **Secrets** 新建 `OPENAI_API_KEY`，值为你的 OpenAI API Key。不要把密钥写入代码或公开文件。
2. 在 **Variables** 可选新建 `OPENAI_MODEL`。默认使用 `gpt-5-mini`，可根据账户可用模型修改。
3. 在 **Variables** 可选新建 `AI_MAX_NEW_SUMMARIES`。默认每次最多新增 20 篇摘要，避免第一次运行产生过多调用；之后每小时继续处理剩余文章。

没有配置 API Key 时，普通 RSS 仍会正常生成，AI 摘要源暂时为空。AI 调用失败也不会阻断抓取和发布。

部署完成后，首页地址通常是：

```text
https://你的GitHub用户名.github.io/science-rss/
```

主要订阅地址：

```text
https://你的GitHub用户名.github.io/science-rss/all.xml
https://你的GitHub用户名.github.io/science-rss/softmatter.xml
https://你的GitHub用户名.github.io/science-rss/active_matter.xml
https://你的GitHub用户名.github.io/science-rss/condensed_matter.xml
https://你的GitHub用户名.github.io/science-rss/all_ai.xml
https://你的GitHub用户名.github.io/science-rss/softmatter_ai.xml
```

## 调整筛选规则

只需修改 `config/topics.yml`：

- `include`：关键词及权重；数值越大越重要
- `exclude`：该主题下需要排除的歧义词
- `source_boost`：对天然属于某主题的来源加基础分（例如 Phys.org Soft Matter）
- `global_exclude`：全部主题共同排除的噪声词
- `title_multiplier`：标题命中的倍率，默认 3
- `summary_multiplier`：摘要命中的倍率，默认 1
- `minimum_score`：进入主题 RSS 的最低分数

例如希望更关注 odd viscosity，可以在 `softmatter.include` 下添加：

```yaml
odd viscosity: 5
odd mobility: 5
奇黏性: 5
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
pytest -q
python build.py --base-url https://example.com/science-rss/
```

输出位于 `docs/`。首次运行时，暂时无法访问的来源可能是 0 条；后续运行会使用 `.cache/state/` 中的上次成功结果。

AI 摘要缓存位于 `.cache/ai_summaries/`，由 GitHub Actions 缓存自动保存。推荐在 RSS 阅读器中订阅 `all_ai.xml`；这个源只收录已经完成 AI 摘要的文章，从而保证“先总结，再推送”。

## 故障判断

首页显示“使用缓存”时，说明该来源本轮抓取失败，但订阅内容仍保留。查看 `health.json` 的 `error` 字段即可定位超时、网站改版或解析规则失效。其他来源不会受影响。

## 注意

请保持合理抓取频率。本项目默认每小时一次，适合个人使用。若网站条款禁止自动抓取，应停用对应来源或改用其官方 RSS/API。
