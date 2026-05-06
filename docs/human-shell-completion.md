# Human Shell Completion

Human Shell v1.5 提供轻量 Tab completion。目标是让日常输入更接近文件系统式操作，但仍保持实现简单、只读、安全。

## Implementation

`tm shell` 启动时会尽量加载 Python 标准库 `readline`，并注册 shell completer。macOS 上可能由 libedit 提供 readline 兼容层，因此双 Tab 展示候选的细节会随平台略有差异。

如果 readline 不可用，shell 仍可正常运行，只是没有原生 Tab completion。用户仍可使用 fallback：

```text
complete cd 出
complete provider d
complete accept
```

## Supported Completions

支持范围：

- shell commands；
- virtual paths；
- project names；
- project nodes in current project；
- mini projects；
- object targets for `show` / `open` / `done` / `note` / `result` 等；
- session-local Proposal numbers；
- provider names；
- quality report names；
- `preview` / `detail` 的 `on` / `off`。

示例：

```text
c<Tab>
cd /p<Tab>
cd /projects/韩<Tab>
cd 出<Tab><Tab>
done 打<Tab><Tab>
accept <Tab><Tab>
quality m<Tab><Tab>
provider d<Tab><Tab>
preview o<Tab>
```

## Double Tab

唯一候选时，readline 会补全该候选。多候选时，readline / libedit 通常会在双 Tab 后显示候选列表。

由于不同平台对双 Tab 展示的控制能力不同，本项目保证：

- 单一候选可通过 completer 返回；
- 多候选可通过 readline 原生机制展示；
- 原生展示不可用时，可用 `complete <partial line>` 查看候选；
- 候选不超过前 20 个，过多时请继续输入缩小范围。

## Safety Boundary

Completion 是只读操作：

- 不调用 provider；
- 不写 Logseq；
- 不 apply Proposal；
- 不修改数据库；
- 不展示 API key、token、password、secret 等敏感值。

Completion 与执行期 target selection 是两层不同保护。即使 Tab 帮用户补全了部分文本，执行 `done 打车`、`cd 韩国` 等仍会在不唯一时展示候选并等待选择。

## Text Handling

中文候选按普通字符串前缀匹配。项目名、节点名或对象标题包含空格时，completion 会返回原始候选；实际执行命令时建议用引号包住。名称中包含 `/` 时不会崩溃，但路径语义可能需要更明确的上下文或候选选择来消除歧义。
