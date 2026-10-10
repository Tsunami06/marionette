# AI Game Companion

基于 [Carey8175/Sunflower](https://github.com/Carey8175/Sunflower) 改造的金铲铲 AI 陪玩基础项目。
当前版本用于验证：**连接模拟器 → 截图 → 识别局势 → 预览或执行一次购买 → 检查结果**。

v0.2 增加 S18/18.3 候选资料、同名棋子身份保留、已知仙灵分类、独立截图诊断、离线 OCR 回放和截图区域校准。
开发计划与当前完成状态见 [docs/control-plan.md](docs/control-plan.md)。

这是操作与观察 MVP。尚未实现完整对局接管、完整棋盘/备战席跟踪、装备分配、队友观察或语音陪聊。
新入口默认只观察、预览；旧控制模块仍保留原有操作接口。

## 已实现

- 可配置的 ADB 地址、画面尺寸、OCR 区域、英雄数据、目标英雄、金币保留和操作次数。
- 一次截图、一次整屏 OCR，统一解析金币、等级、阶段和五格商店；每张图有时间与唯一 ID。
- 名称精确匹配优先；模糊匹配设置最低阈值和歧义门槛，未知名称返回未知。
- 数字解析失败不会当成有效金币或等级；画面尺寸不匹配时不执行购买。
- 准备阶段判断、过期画面检查、金币保留、售价检查、操作次数限制。
- 购买前重新观察，防止策略使用旧商店；观察和操作共用一把异步锁。
- 默认 dry-run，必须显式使用 `--execute` 才发送输入。
- 执行前必须完成当前英雄数据核对；操作结果不确定则暂停，不自动重试点击。
- 保存原始截图、OCR 文字框、局势快照、操作前后 ID 和暂停原因。
- 修复上游入口空逻辑、嵌套事件循环、尺寸/密度返回类型、缺失 await、空 OCR 处理等问题。
- 不连接游戏即可运行的单元测试与 Python 3.11/3.12 CI。
- 按 ID 保留同名棋子；拉克丝形态可以通过单独配置的商店羁绊区域识别，身份不明时阻止购买。
- 已知自然仙灵名称会标记为 `charm`；不会被目标英雄购买流程点击。未知内容仍返回未知。
- 彩色截图和 `capture`/`ocr` 分项耗时日志；截图/设备诊断不初始化 OCR 模型。
- `catalog`、`replay`、`calibrate` 可离线使用，无须设备或 OCR 依赖。

## Windows 安装

建议使用 Python 3.11 的独立虚拟环境，避免 OCR 依赖影响其他项目。
项目支持 Python 3.11/3.12；真实 OCR 依赖组合仍需在你的机器上验证。
解压或克隆项目后，在项目根目录运行以下命令。

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[device]"
Copy-Item config/example.toml config/local.toml
```

使用 PaddleOCR 2.x 接口，依赖范围已限制到 `<3`。首次初始化会下载 OCR 模型，需要联网。
如果平台无法安装 PaddlePaddle，请保留观察核心并先解决对应 Python/平台的安装兼容性。
如果先验证设备和截图，可只安装 `python -m pip install -e ".[transport]"`，然后运行 `doctor --capture-only`、`probe`、`capture`。

## 第一轮验证

1. 在模拟器里开启 ADB，确认实际端口；修改 `config/local.toml` 的 `host` 和 `port`。不会扫描其他端口。
2. 手动启动游戏进入对局。程序不会替你登录、启动游戏或匹配。
3. 运行下面的检查和截图命令。

```powershell
python -m companion.cli --config config/local.toml doctor
python -m companion.cli --config config/local.toml probe
python -m companion.cli --config config/local.toml capture
```

`doctor` 只检查依赖和文件，不证明 ADB 已连通；`capture` 会连接设备并保存截图。
`probe` 会验证连接、保存彩色截图，并返回实际截图尺寸、设备报告的尺寸和 DPI；不点击游戏、不加载 OCR。
程序不会自动修改模拟器分辨率/DPI。模板坐标来自上游 1024×720 布局，未在当前游戏验证。
根据实际截图设置 `width`/`height`，并修改 `config/layout.json` 的 `[x, y, width, height]` 区域。
改变分辨率不能保证布局仍正确，必须重新核对。

可把 `capture` 或 `probe` 返回的 PNG 路径填入下列命令，生成本地坐标编辑页面：

```powershell
python -m companion.cli --config config/local.toml calibrate --image "runs/<会话>/<截图>.png" --output "runs/calibration.html"
Start-Process "runs/calibration.html"
```

在页面里选择字段并拖动框选，导出 `layout.json` 后替换 `config/layout.json`；将本地配置的 `width`、`height` 改为实际截图尺寸。
商店 `store` 区域只框名称；可选 `store_details` 是五个独立羁绊区域，未校准的位置填 `null`，不自动推断拉克丝形态。
页面生成仅支持 PNG，完全离线；导出不会自动修改配置或声明实机核验完成。

4. 读取一次局势，对照原始截图检查每个字段。

```powershell
python -m companion.cli --config config/local.toml observe
```

`phase` 为 `unknown` 时先检查 OCR 原始文字和界面，不要直接放宽操作条件。
当前阶段识别依赖“备战环节”“战斗环节”等文字，特殊界面识别并不完整。

5. 核对当前英雄名称和售价，再预览一次购买。

```powershell
python -m companion.cli --config config/local.toml buy --slot 2
```

商店序号在 CLI 中是 1～5。默认不发送点击。
`reserve_gold` 默认 20，所以购买后金币不足 20 时会被阻止；可根据验证需求修改。

## 当前赛季数据

默认示例配置已指向 `companion/data/s18-18.3.json`：74 条棋子记录（65 个名称，拉克丝含多个形态）、36 个羁绊、253 个强化和 169 个仙灵基础条目。
来源是社区资料库；官方公告与赛季介绍用于交叉核对。文件保留来源链接、抓取日期、原始内容摘要和字段来源；这些是候选资料，**尚未经过实机核验**。
仙灵不是已确认的完整清单，部分出现回合和条件沿用旧补丁，保留 `provenance`，不可据此执行购买；技能数值与强化文本仅用于参考。
本轮未导入装备数据。上游 `sunflower/statics/` 的旧数据仍保留供兼容，标注时间为 2024 年 11 月。
不会自动更新数据，也不会自动把 `current_data_verified` 设为 true。
逐项核对实际赛季、名称、售价与画面后，才在本地配置设置 `current_data_verified = true`。
这个开关是用户的核对声明，程序不能替你证明赛季正确。

查看资料不需要设备：

```powershell
python -m companion.cli --config config/local.toml catalog
python -m companion.cli --config config/local.toml catalog --name "拉克丝"
```

新的资料格式使用 `metadata`、`champions`、`traits`、`augments`、`charms`，棋子按 ID 保留。旧英雄文件格式仍兼容，最小示例：

```json
{
  "season": "你实际验证的版本",
  "time": "你核对数据的日期",
  "data": {
    "example-id": {"name": "实际英雄名称", "buyPrice": "3"}
  }
}
```

不要把示例名称直接作为游戏数据。缺失或无效售价会阻止相关购买。
海克斯/装备的上游读取接口保留，但新自动循环尚不处理它们。

资料导入工具可复现转换，不会联网或改动执行开关：

```powershell
python scripts/import_season.py <下载的原始JSON> companion/data/s18-18.3.json --fetched-at 2026-10-10
```

此工具专用于本次已审阅的 S18/18.3 档案；新赛季需要先审阅来源和版本，再调整导入工具。

## 离线回放

保存的 `events.jsonl` 可重复解析，调整布局与匹配规则时无需重新连接游戏：

```powershell
python -m companion.cli --config config/local.toml replay --ocr "runs/<会话>/events.jsonl"
python -m companion.cli --config config/local.toml replay --ocr "runs/<会话>/events.jsonl" --frame-id <截图ID>
```

默认选择最后一个 OCR 记录，也接受包含 `frame_id`、`captured_at`、`width`、`height`、`boxes` 的单帧 JSON。
旧日志缺失尺寸时，可用 `--image <对应PNG>`提供尺寸证据；没有尺寸或截图时间时会标记为未核验。
回放保留原始时间，不把历史画面变成实时状态；入口不会连接设备，也不会发送输入。

## 一次真实购买

完成布局和当前数据核对后：

```powershell
python -m companion.cli --config config/local.toml buy --slot 2 --execute
```

购买结果 `verified` 的含义限定为：同一准备回合内，金币恰好减少售价，目标格没有再识别到名称，
且主要字段完整、截图未过期。**这是购买的两项画面证据，不是完整的备战席或合成确认。**
OCR 漏识别、其他人同时操作、特殊机制仍可能干扰证据。第一轮必须人工对照保存的前后截图。
备战席容量、棋子合成和领取位置的独立验证是下一阶段工作。
不满足证据则 `paused`，需要人工检查后重新启动；不会盲目再次点击。
`max_actions = 1` 默认限制每次会话最多发送一次购买尝试。

## 有限观察循环

在本地配置设置 `targets = ["已核对的目标英雄"]`：

```powershell
python -m companion.cli --config config/local.toml run --iterations 10
```

默认只预览。加 `--execute` 可在准备阶段按目标名单尝试购买，仍受上述条件与总操作次数限制。
未知界面、已识别选择界面会暂停，结算会结束。此循环不会自动升级、D 牌、布阵或选海克斯。
按 Ctrl+C 停止。日志写入 `runs/<会话时间-ID>/`，包含截图与 `events.jsonl`，已排除在 Git 提交之外。

## 测试

核心测试只需要 Python 标准库，不连接设备、不加载模型、不发送任何游戏输入：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q companion sunflower
```

`sf_tests/` 是上游手动调试脚本，部分会移动或出售棋子，不属于自动化测试集。不要批量运行。
真实设备、OCR 模型加载、当前布局、当前赛季和完整对局尚未实测。

## 目录与后续工作

| 目录 | 内容 |
|---|---|
| `companion/` | 新 CLI、配置、单帧解析、串行会话和购买证据检查 |
| `sunflower/` | 保留并修复的上游 ADB/OCR 与控制模块 |
| `config/` | 设备、局势读取区域与运行限制 |
| `tests/` | 不依赖模拟器的回归测试 |
| `sf_tests/` | 上游手动示例，可能发送真实输入 |

下一阶段：当前布局实测、备战席/棋盘持续跟踪、装备处理、选择界面状态机、固定阵容完整对局、
队友观察后返回校验、基于真实局势事件的 AI 语音陪聊。
陪玩产品应清楚说明 AI 身份。

上游来源、基线提交与版权见 [NOTICE](NOTICE)，MIT 许可见 [LICENSE](LICENSE)。
