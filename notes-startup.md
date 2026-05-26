# 2026-05-26

## 安装 AnySearch Skill
- Calvin 要求安装 GitHub 上的 `anysearch-ai/anysearch-skill`（统一实时搜索引擎）
- 已安装到 `~/.agents/skills/anysearch/`，Python runtime 已配置
- 验证搜索"生益科技 摩根大通"成功返回结果
- **重要:** 以后专业搜索（股票、深度查询等）优先用 AnySearch，替代 web_search

## 之前的工作
- 查找摩根大通购买生益科技股票的原因和相关报告
  - 没有找到摩根大通单独发研报的记录
  - 但找到了高盛（Buy, TP 127.4）和花旗（Buy, TP 83）的研报
  - AnySearch 搜到摩根大通证券(中国) 出现在生益科技的机构列表中
- 写了 topbank_tracker.py 脚本用于追踪顶级投行对 A 股的关注度
