<h1 align="center">JavLib</h1>

<p align="center">
  <b>轻量、安全优先的 JAV NAS 媒体库建设工具。</b>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache 2.0"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-lockfile-DE5FE9" alt="uv"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

JavLib 用于整理 NAS 上的 JAV 媒体库：从文件夹名识别番号，或直接输入番号，查询 JavBus 与 JavDB，默认由 Jav321 补充可用的剧情简介，并生成媒体中心可读取的 NFO 与图片。视频同名 NFO 适配绿联 UGOS 影视中心（需开启「优先读取本地信息」），文件夹级 `movie.nfo` 兼容 Emby / Jellyfin / Kodi。

---

## 目录

- [安装](#安装)
- [媒体库结构](#媒体库结构)
- [命令参考](#命令参考)
- [快速开始](#快速开始)
- [生成的文件](#生成的文件)
- [元数据来源与合并规则](#元数据来源与合并规则)
- [文件夹与视频改名](#文件夹与视频改名)
- [隐私](#隐私)
- [测试](#测试)
- [已知限制](#已知限制)
- [许可证](#许可证)

---

## 安装

```bash
git clone https://github.com/syy674998887/JavLib.git
cd JavLib
uv sync
uv run javlib --help
```

支持 Python 3.11+；macOS、Windows 与 Linux 使用相同命令。

---

## 媒体库结构

`--dir` 指定媒体库根目录。程序只扫描其下的一级文件夹，番号从文件夹名中识别，不会递归处理更深层目录。隐藏文件夹会被忽略；无法识别番号的文件夹会由 `inspect` 报告，`scrape` 和两种 `rename-*` 不处理。

```text
/path/to/JAV/
├── SONE-035/
│   └── SONE-035.mp4
├── IPVR-256-C/
│   └── IPVR-256-C.mkv
└── FC2-PPV-1234567/
    └── FC2-PPV-1234567.mp4
```

番号规范化只用于查询和 NFO；`-C`、`-U`、`-UC`、`-leak` 等文件夹语义会写入 NFO 标签，`scrape` 不会改变文件夹或视频名称。以数字开头的番号前缀会完整保留，例如 `3DSVR-1823`、`300MIUM-001`。

程序只识别一级文件夹内的视频文件，扩展名不区分大小写：

`.mp4` `.mkv` `.avi` `.wmv` `.mov` `.m4v` `.ts` `.iso` `.rmvb` `.flv`

视频文件名无需与文件夹名一致。同一文件夹内的多个受支持视频共用文件夹元数据，并分别生成视频同名 NFO。

---

## 命令参考

```bash
uv run javlib COMMAND [OPTIONS]
```

| 命令 | 用途 |
| --- | --- |
| `scrape` | 查询元数据并生成 NFO 与图片 |
| `get CODE [CODE ...]` | 直接按番号刮削到 `output/`，无需本地视频 |
| `inspect` | 显示从文件夹名识别的查询番号与标签 |
| `rename-folders` | 标准化一级文件夹名称 |
| `rename-videos` | 清理视频及匹配附属文件的名称 |
| `undo-folders` | 回滚最近一批文件夹改名 |
| `undo-videos` | 回滚最近一批视频改名 |

> [!IMPORTANT]
> `inspect` 不联网、不写盘。`scrape` 和 `get` 会联网并写入 NFO 与图片，但不会删除或改写视频。两种改名和两种回滚命令默认只预览，必须提供 `--apply` 才会执行。

### 目录与筛选

| 参数 | 可用命令 | 用途 |
| --- | --- | --- |
| `--dir PATH` | 除 `get` 外的全部命令 | 媒体库根目录；未提供时读取 `JAVLIB_DIR` |
| `--limit N` | `scrape`、`inspect`、两种 `rename-*` | 在应用 `--only` 后，最多处理按文件夹名不区分大小写排序的前 N 项；`0`（默认）表示全部 |
| `--only NAME` | `scrape`、`inspect`、两种 `rename-*` | 只处理指定番号对应的一级文件夹；`NAME` 必须是完整文件夹名且区分大小写，可重复提供 |

旧环境变量 `JAVLIBRARIAN_DIR` 仍兼容。媒体库路径的优先级为：`--dir`、`JAVLIB_DIR`、`JAVLIBRARIAN_DIR`。

### 刮削

以下参数适用于 `scrape` 和 `get`：

| 参数 | 用途 |
| --- | --- |
| `--force` | 重新处理已有 `movie.nfo` 的文件夹，并替换本次成功生成的同名 NFO 与图片 |
| `--page-delay SECONDS` | 同一元数据来源连续页面请求之间的基础间隔；默认 `5.0` 秒，各来源分别计时 |
| `--image-delay SECONDS` | 同一图片主机连续请求之间的基础间隔；默认 `2.0` 秒 |
| `--delay SECONDS` | 联网刮削的影片之间的间隔；默认 `10.0` 秒 |
| `-v`、`--verbose` | 显示请求等待、影片间等待、自动减速和重试信息 |

延迟值必须是有限的非负数。`0` 只关闭对应的基础间隔，重试退避仍可能等待。

HTTP 408、429、500、502、503、504 与网络异常最多重试 5 次。退避从 10 秒开始逐次翻倍，最高 300 秒；429 的纯数字 `Retry-After` 会优先采用。每次 429 或 503 会将受影响的非零「主机 + 请求类型」基础间隔乘以 1.5，最高 30 秒；用户设置的间隔若高于此上限，则保留原值。其他 4xx 不重试。

`scrape` 和 `get` 在全部成功或跳过时返回退出码 `0`，有任一番号失败时返回 `1`，中断时返回 `130`。单个番号失败不会阻止后续番号继续处理。

### 按番号导出

`get` 接受一个或多个纯番号，例如 `SONE-035`、`3DSVR-1823`、`FC2-PPV-1234567`。也支持小写、下划线分隔及 `sone00035` 这类 DMM 内容 ID；相同的规范化番号只处理一次。

默认自动创建当前工作目录下的 `output/{规范化番号}/`，无需预先准备视频或文件夹。用 `-o PATH` 或 `--output PATH` 指定输出根目录；此命令不使用 `JAVLIB_DIR`。默认的项目 `output/` 已被 Git 忽略。

每个番号生成 `movie.nfo`，并保存成功下载的 `fanart.jpg`、`poster.jpg` 和 `Samples/` 剧照。已有 `movie.nfo` 时跳过，添加 `--force` 可重新刮削。

### 改名与回滚

| 参数 | 可用命令 | 用途 |
| --- | --- | --- |
| `--apply` | 两种 `rename-*`、两种 `undo-*` | 执行当前显示的改名或回滚计划 |
| `--journal PATH` | 两种 `rename-*`、对应的 `undo-*` | 指定回滚日志；默认位于媒体库根目录；自定义路径回滚时需使用同一文件 |

每次 `undo-*` 只处理对应日志中的最近批次；再次运行可继续回滚上一批。

---

## 快速开始

```bash
uv run javlib inspect --dir "/path/to/JAV"
uv run javlib scrape --dir "/path/to/JAV"
```

无需本地视频，直接按番号导出：

```bash
uv run javlib get SONE-035
uv run javlib get SONE-035 IPVR-256
uv run javlib get SONE-035 --output "/path/to/export" --force
```

第一条命令默认写入 `output/SONE-035/`。

---

## 生成的文件

```text
SONE-035/
├── SONE-035.mp4
├── SONE-035.nfo
├── movie.nfo
├── fanart.jpg
├── poster.jpg
└── Samples/
    ├── sample1.jpg
    └── ...
```

| 文件 | 作用 |
| --- | --- |
| `{视频名}.nfo` | 供按视频同名 NFO 读取的媒体中心使用，如绿联 UGOS 影视中心 |
| `movie.nfo` | 兼容 Emby / Jellyfin / Kodi 的文件夹级 NFO，同时作为刮削完成标记 |
| `fanart.jpg` | 横版封面 |
| `poster.jpg` | 竖版海报 |
| `Samples/` | 页面剧照 |

图片处理和视频同名 NFO 写入完成后，程序最后原子写入 `movie.nfo`。图片无法下载不会阻止元数据输出，可用 `--force` 重试补图。执行中断时未生成 `movie.nfo` 的文件夹会在下次运行重新处理。

---

## 元数据来源与合并规则

元数据来源为 [JavBus](https://www.javbus.com) 和 [JavDB](https://javdb.com)。只命中一个来源时直接使用该来源；双源都命中时以 JavBus 为主记录，由 JavDB 补充缺失字段和备用图片。

`scrape` 和 `get` 默认还会查询 [Jav321](https://www.jav321.com)，将剧情简介写入 NFO 的 `<plot>`。该来源只补充简介，不覆盖标题、演员或图片；至少一个主来源命中后才查询。简介缺失、番号校验失败或请求失败时，仍正常输出原有元数据；简介请求只尝试一次。已有 `movie.nfo` 仍按原规则跳过，需要补充简介时使用 `--force` 重新刮削。

### 来源校验

从来源详情页实际解析出的番号必须与本地规范化番号一致；页面番号缺失或为空时拒绝该来源。常规字母加数字番号的比较不区分大小写和分隔符，并忽略数字部分的前导零，例如 `IPVR-256` 与 `ipvr_0256` 视为相同。两站都没有有效结果或处理发生异常时，该文件夹会报告失败。

Jav321 必须在同一元数据区块中提供唯一、完整且匹配的「品番」以及唯一的非空简介；不会拿搜索词、标题或 URL 代替身份校验。数字前缀不能省略：页面的 `MIUM-865` 既不能确认 `300MIUM-865`，也不能确认 `999MIUM-865`。番号不完整或存在歧义时直接跳过，宁可保留空简介。

### 字段合并

| 数据 | 合并规则 |
| --- | --- |
| 标题 | JavBus 标题写入 `originaltitle`；JavDB 标题不含日文假名时用作显示标题，否则使用主记录标题 |
| 发行日期、时长、制作商、发行商、导演、系列 | 保留 JavBus 已有值，仅用 JavDB 填补空缺 |
| 类别 | 合并两站类别并去重，JavBus 顺序在前 |
| 演员 | 使用 JavBus 演员与头像；仅在 JavBus 没有演员时使用 JavDB 女优名单 |
| 剧情简介 | 完整番号校验通过后使用 Jav321；不可用时不写入 `<plot>` |
| 封面 | JavBus 为主源；下载失败时尝试 JavDB 封面 |
| 剧照 | JavBus 为主源，JavDB 同序号图片作为备源；JavBus 没有剧照时使用 JavDB |
| 数据源标记 | 主来源按实际命中结果写为 `javbus`、`javdb` 或 `javbus+javdb`；仅在使用简介时追加 `+jav321` |

### 图片与海报

图片下载失败、无法解码或短边不足 200 像素时不会覆盖已有文件；存在备用来源时继续尝试。有效图片通过临时文件校验后再写入目标。

- 普通影片从横版封面右侧裁取宽度的 47.5% 作为 `poster.jpg`。
- VR 影片优先以 DMM `ps.jpg` 为参照，从剧照中识别竖版封面；没有可用参照时选择第一张竖图，最后再回退到横版封面裁剪。

---

## 文件夹与视频改名

文件夹与视频工作流使用独立的回滚日志。每项改名会在触碰文件系统前原子写入日志；回滚时会区分已完成、未开始和部分完成的记录。

日志默认保存在媒体库根目录（`folder_rename_log.json`、`video_rename_log.json`），随媒体库一起走：macOS、Windows、Linux 以不同路径挂载同一共享时都能读取，在一台电脑上改名，可以在另一台电脑上回滚。用 `--journal` 放在媒体库以外的日志仍绑定写入时的媒体库路径。旧版本把日志写在运行目录，移到媒体库根目录即可继续回滚。

视频及其同名字幕（包括 `SONE-035.chs.srt` 这类带语言标记的字幕）、视频同名 NFO 会作为一组处理；同名前缀匹配不区分大小写，文件夹级 `movie.nfo` 不参与改名。任一目标已被占用时整组跳过；回滚不会覆盖现有文件。

改名命令目前会将 `-leak` 统一为 `-U`。之后刮削改名后的文件夹会生成「无码破解」标签；保留原来的 `-leak` 名称则生成「无码流出」标签。

---

## 隐私

- 刮削会向 JavBus 与 JavDB 发送番号查询，主来源命中后再向 Jav321 查询简介，并下载主来源页面引用的图片。
- 改名回滚日志包含媒体库路径和媒体文件名，默认保存在媒体库根目录，不会写入项目目录；自定义路径需自行保护。

---

## 测试

```bash
uv run --group test pytest
```

测试完全离线，不访问真实元数据站点。

### 每日网站格式检查

`main` 上的工作流已配置为每天按纽约时间 08:23 检查真实网站，也可手动触发。PR 更新只运行离线测试；定时与手动的在线任务串行执行。

`scripts/check_live_sources.py` 调用项目的实际抓取函数，每站检查一个固定样例（默认 `SONE-035`）。JavBus、JavDB 校验番号、标题、日期、时长、制作商、演员、类别及封面/剧照 URL；Jav321 校验完整番号和简介。正常情况下 JavBus 请求一次，JavDB 请求搜索和详情页两次、间隔至少 5 秒；Jav321 发出搜索 POST，通常自动跳转到详情页，直接解析该响应，不重复请求详情页。不下载图片、不扫描或写入媒体库。

- `PASS`：样例的必需字段均可解析。
- `PARSE_ERROR`：元数据缺失或异常，需要检查网页结构、解析规则或样例是否仍可用。
- `ACCESS_BLOCKED`：登录跳转、验证页或 HTTP 401/403/429；停止请求，不重试。
- `NETWORK_ERROR` / `HTTP_ERROR`：网络或 HTTP 请求失败；短暂故障最多重试一次。
- `CHECK_ERROR`：检查脚本或解析器出现其他异常。

任何非 `PASS` 结果都会使任务失败，并在 Actions 摘要中说明原因，避免把无法验证的网站标为正常。此检查用于发现样例中的字段回归，不保证覆盖所有影片或图片下载问题。

手动本地检查：`uv run python scripts/check_live_sources.py`。可用 `JAVBUS_SMOKE_CODE`、`JAVDB_SMOKE_CODE`、`JAV321_SMOKE_CODE` 更换样例，但需选择已收录且对应来源必需字段完整的影片。

---

## 已知限制

- 元数据解析依赖 JavBus、JavDB 与 Jav321 当前的 HTML 结构。部分 Jav321 页面没有简介，或省略了番号前缀，这些页面不会用于补充简介。
- 请求有意串行且保守，大型媒体库需要较长时间。

---

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。
