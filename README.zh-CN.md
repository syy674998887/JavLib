# JavLib

[English](README.md) · **简体中文**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![uv](https://img.shields.io/badge/uv-lockfile-DE5FE9)](https://docs.astral.sh/uv/)

JavLib 是 JAV 媒体库命令行工具，支持按番号或本地目录刮削元数据、生成 NFO 与图片，以及文件改名和回滚。

- [安装与快速开始](#安装与快速开始)
- [命令与参数](#命令与参数)
- [目录与输出](#目录与输出)
- [数据来源](#数据来源)
- [改名与回滚](#改名与回滚)
- [测试](#测试)
- [许可证](#许可证)

## 安装与快速开始

运行环境：Python 3.11+、[uv](https://docs.astral.sh/uv/)。支持 Windows、macOS 和 Linux。

```bash
git clone https://github.com/syy674998887/JavLib.git
cd JavLib
uv sync
```

### 按番号导出

无需本地视频，直接指定番号和输出目录：

```bash
uv run javlib get SONE-035 IPVR-256 -o "/path/to/output"
```

### 刮削本地媒体库

先检查番号识别结果，再刮削：

```bash
uv run javlib inspect --dir "/path/to/JAV"
uv run javlib scrape --dir "/path/to/JAV"
```

## 命令与参数

用法：`uv run javlib COMMAND [OPTIONS]`。查看单个命令帮助：`uv run javlib COMMAND --help`。

| 命令 | 用途 |
| --- | --- |
| `get CODE [CODE ...]` | 按番号导出元数据与图片 |
| `scrape` | 刮削本地媒体库 |
| `inspect` | 检查目录番号与标签；只读、不联网 |
| `rename-folders` | 规范化文件夹名 |
| `rename-videos` | 清理视频及匹配附属文件名 |
| `undo-folders` | 回滚文件夹改名 |
| `undo-videos` | 回滚视频改名 |

`scrape` 和 `get` 会联网并写入元数据与图片，不修改视频内容或名称。

### 目录与筛选

| 参数 | 适用命令 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--dir PATH` | 除 `get` 外的全部命令 | `JAVLIB_DIR`，否则必填 | 媒体库根目录，显式参数优先 |
| `-o, --output PATH` | `get` | `./output` | 输出根目录，不读取 `JAVLIB_DIR` |
| `--only NAME` | `scrape`、`inspect`、`rename-*` | 全部 | 精确匹配完整文件夹名，区分大小写，可重复指定 |
| `--limit N` | `scrape`、`inspect`、`rename-*` | `0`（全部） | 筛选后按目录名排序取前 N 项，排序不区分大小写 |

`get` 支持多个番号，例如 `SONE-035`、`3DSVR-1823`、`FC2-PPV-1234567`；也接受小写、下划线和 DMM 编号（如 `sone00035`），规范化后去重。

### 刮削

以下参数适用于 `scrape` 和 `get`：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--force` | 关闭 | 重新刮削已有 `movie.nfo` 的目录，替换本次成功生成的同名 NFO 与图片 |
| `--page-delay SECONDS` | `10` 秒 | 同一网站页面请求的基础间隔 |
| `--image-delay SECONDS` | `2` 秒 | 同一图片主机请求的基础间隔 |
| `--delay SECONDS` | `10` 秒 | 一部处理结束到下一部开始联网的间隔 |
| `-v, --verbose` | 关闭 | 显示等待、自动减速与重试信息 |

页面和图片请求分别按主机计时，只等待不足的间隔。延迟参数接受非负有限数值；`0` 关闭对应的基础等待，错误重试仍可能等待。

请求串行执行。主元数据和图片请求遇可重试故障时，最多尝试 **5 次（含首次）**；Jav321 简介请求仅尝试一次。

退出码：`0` 全部成功或跳过，`1` 有影片失败，`130` 用户中断。单部失败不终止批次。

## 目录与输出

本地刮削与改名仅处理根目录下的一级文件夹，番号从文件夹名识别。隐藏目录和无法识别番号的目录会被跳过；`inspect` 会报告后者。

```text
/path/to/JAV/
├── SONE-035/
│   └── video.mp4
└── IPVR-256-C/
    └── IPVR-256-C.mkv
```

同一目录内的视频共用元数据，视频文件名无需与目录名一致。文件夹后缀 `-C`、`-U`、`-UC`、`-leak` 会转换为 NFO 标签。

支持的扩展名不区分大小写：`.mp4`、`.mkv`、`.avi`、`.wmv`、`.mov`、`.m4v`、`.ts`、`.iso`、`.rmvb`、`.flv`。

`scrape` 写入原影片目录；`get` 自动创建 `<输出根目录>/<规范化番号>/`。无视频时只生成元数据与图片。

| 文件 | 用途 |
| --- | --- |
| `{视频名}.nfo` | 存在视频时生成；绿联 UGOS 影视中心需开启「优先读取本地信息」 |
| `movie.nfo` | 文件夹级元数据，兼容 Emby / Jellyfin / Kodi；同时标记刮削完成 |
| `fanart.jpg` | 横版封面 |
| `poster.jpg` | 竖版海报 |
| `Samples/` | 剧照 |

已有 `movie.nfo` 的目录默认跳过。中断后尚未生成此文件的目录，下次运行会重新处理。图片下载或校验失败时保留已有图片，不阻止 NFO 输出。

普通影片的海报由封面裁剪生成；VR 影片优先使用合适的竖版剧照，否则裁剪封面。

## 数据来源

| 来源 | 用途 |
| --- | --- |
| [JavBus](https://www.javbus.com) | 主元数据与图片 |
| [JavDB](https://javdb.com) | 补充元数据与备用图片 |
| [Jav321](https://www.jav321.com) | 默认补充剧情简介，写入 `<plot>` |

至少 JavBus 或 JavDB 命中一个有效结果才会输出。仅命中一站时使用该站记录；双源命中时保留 JavBus 字段，由 JavDB 补缺。类别合并去重，演员优先使用 JavBus；JavDB 不含日文假名的标题可用作显示标题，JavBus 标题保留为原始标题。

**详情页必须提供完整、匹配的番号。** 常规番号比较忽略大小写、分隔符和末尾数字的前导零，但保留数字前缀：`MIUM-865` 不能代替 `300MIUM-865`。番号缺失、不匹配或 Jav321 结果有歧义时拒绝该来源。

Jav321 在主来源命中后查询，仅补充简介；缺失或查询失败不影响其他元数据输出。部分页面没有简介或省略番号前缀，因此不会生成 `<plot>`。

刮削会向上述站点发送查询番号并访问图片地址。解析依赖站点 HTML，可能因页面变更或访问限制失败。

## 改名与回滚

两种 `rename-*` 和两种 `undo-*` 命令均支持以下参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--apply` | 关闭 | 执行改名或回滚；默认只预览 |
| `--journal PATH` | 媒体库根目录中的对应日志 | 自定义日志路径，回滚时需指定同一文件 |

预览视频改名：

```bash
uv run javlib rename-videos --dir "/path/to/JAV"
```

- 视频、同名字幕（含语言后缀）及 NFO 成组改名，匹配前缀不区分大小写；`movie.nfo` 不参与。目标冲突时整组跳过，回滚不覆盖已有文件。
- 文件夹与视频分别使用 `folder_rename_log.json`、`video_rename_log.json`。每次实际回滚处理最近一批，成功后可继续回滚上一批。
- 日志记录路径和文件名，需保留以供回滚。库内日志可随媒体库迁移；库外自定义日志绑定原媒体库路径。
- 改名将 `-leak` 转为 `-U`：原名刮削标记「无码流出」，改名后刮削标记「无码破解」。

## 测试

离线测试：

```bash
uv run --group test pytest
```

真实网站检查：

```bash
uv run python scripts/check_live_sources.py
```

GitHub Actions 计划于每天 **08:23（America/New_York）** 检查三站，也可手动触发；PR 只运行离线测试。每站默认检查 `SONE-035`，校验番号及对应来源的必需字段，包括 Jav321 简介；不下载图片或写入媒体库。

任何非 `PASS` 结果都会使检查失败，Actions 摘要会区分解析异常、访问限制、网络/HTTP 错误和脚本异常。单一样例不代表全站覆盖。

可用 `JAVBUS_SMOKE_CODE`、`JAVDB_SMOKE_CODE`、`JAV321_SMOKE_CODE` 更换已收录且字段完整的样例。

## 许可证

[Apache License 2.0](LICENSE)
