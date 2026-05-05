# Logseq Adapter

## 扫描范围

Logseq graph path 来自配置，默认会尝试 `/Users/wangrundong/logseq/Logseq_File` 。adapter 扫描：

- `pages/**/*.md`
- `journals/**/*.md`

不扫描 `assets/` 、 `logseq/` 、whiteboard 或 git 数据。

## 已验证的用户习惯

仓库中已有 `logseq_usage_audit.md` 和 `analysis_data.json` ，确认了以下模式：

- Daily Log 是工作日记、任务管理和想法收集箱的混合体。
- TODO 常见格式是 `- TODO ...` ，DONE 是 `- DONE ...` ，DOING 很少。
- 过程记录常写在 TODO 子块下面。
- 项目页常有 `PARA:: [[PARA/Project]]` 和结构标记。
- 项目并不限于 `项目-` 前缀， `任务-` 、 `学习-` 、 `课程-` 、 `阶段-` 也可能是项目。
- 想法常见 `**[想法]** ...` 、 `[想法] ...` 、 `**[随想]** ...` 、 `[随想] ...` 。

## Parser 规则

- 识别 Logseq 缩进 block tree。
- 识别顶部页面属性 `key:: value` 。
- 识别缩进的块属性，例如 `id::` 、 `private:: true` 。
- 保留行号、文件路径、页面名、journal 日期和 block path。
- 识别代码围栏，避免代码块中的 TODO 误判为任务。

## Project 识别

高置信：

- `PARA:: [[PARA/Project]]`
- 页面正文含项目结构标记

中置信：

- 只有 PARA project
- 或只有项目结构标记

低置信：

- 页面名前缀像项目，且包含任务或结构标记

结构标记包括 `[具体目标]` 、 `[具体事务]` 、 `[资源列表]` 、 `[头脑风暴]` 、 `[反思]` 、
`[价值层]` 、 `[目标层]` 、 `[里程碑]` 、 `[阶段]` 、 `[子阶段]` 、 `[待澄清]` 。

## Task 识别

明确 `TODO` / `DOING` / `DONE` 生成 Task。解析 `[#A]` / `[#B]` / `[#C]` 、 `SCHEDULED` 、
`DEADLINE` 、block refs 和 embeds。

纯 `- ((uuid))` 引用行不生成新 Task。结构性 embed 可以通过配置 `ignored_embed_uuids`
标记并忽略。

Task 子块会作为 SourceRecord 保存，并通过 `object_record_links` 关联给 Task。

## Idea 识别

高置信 idea 只来自显式行首 marker：

- `**[想法]** xxx`
- `[想法] xxx`
- `**[随想]** xxx`
- `[随想] xxx`

位于 Task 子块下时关联 Task，位于项目页 `[头脑风暴]` 下时关联 Project，否则作为 free idea。

不抽取：

- `[[想法]]`
- `[[随想]]`
- 普通句子里出现“想法”
- Readwise highlight 等普通摘录，除非有显式 marker
- title 为空、过短、只有符号、以 `]` 开头或只有 wiki link 残片

## 限制

- 无 uuid block 使用文件、行号和内容 hash，移动行可能改变弱身份。
- 第一版解析 Markdown block tree，不执行 Logseq 内部数据库或 UI 语义。
- 高频结构模板需要用户配置 ignored embed uuid。

## Relation 推断

- 项目页内任务 `belongs_to` 项目，confidence `0.9` 。
- 项目页 `[头脑风暴]` 下 idea `belongs_to` 项目，confidence `0.85` 。
- task 子块中的 idea `belongs_to` task，confidence `0.95` 。
- journal task/idea 如果 wiki link 指向已识别项目页， `belongs_to` 项目，confidence `0.75` 。
- journal 纯 block ref 不创建重复 task，而是给被引用对象添加 `journal_exposure` record link。
- structural embed 不当作语义 relation。
