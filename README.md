# dswork-suite

你自己的软件套件：所有自用 Android 应用共用一套设计令牌，风格不再靠人工同步。

## 这套东西解决什么

以前：每个 app 各有一份颜色表，改主色要改两遍，改漏了没人发现。
现在：颜色/圆角/间距/字号只在 `design/tokens.json` 里写一次，跑一次生成，所有 app 同步。

## 目录

```
suite/
  design/
    tokens.json     唯一真源：配色（深/浅）、圆角、间距、字号
    apps.json       注册表：哪个 app、什么类型、颜色名怎么映射
    gen.py          生成器 + 漂移检查（--check）
  tools/
    publish.py            把任意目录推到 GitHub（双参数：--root / --repo）
    sync-all.py           一键：生成 → 校验 → 推送三个仓库
    verify-chinglish.ps1  不改动产物，只验证 ChinGlish 还能编译
```

## 日常怎么用

改风格：

```bash
# 1. 编辑 design/tokens.json
# 2. 生成到所有 app
python D:/.dswork/App/suite/design/gen.py
# 3. 确认一致
python D:/.dswork/App/suite/design/gen.py --check
```

改完重新打包各 app 即可，不需要再逐个改色值。

## 同步到 GitHub

```bash
python D:/.dswork/App/suite/tools/sync-all.py
```

一条命令做三件事：生成令牌 → 校验漂移 → 推送 `Suite`、`ChinGlish`、`ToDoList`、`Inter` 四个仓库。
没设 `GITHUB_TOKEN` 时会提示输入一次（不回显），三个仓库复用。
只想本地生效就加 `--no-push`。

## 新增一个 app

1. 在 `design/apps.json` 的 `apps` 里加一条：

```json
{
  "id": "myapp",
  "title": "MyApp",
  "kind": "android-compose",
  "root": "D:/.dswork/App/MyApp",
  "package": "com.dswork.myapp.ui.theme",
  "outputs": { "kotlin": "app/src/main/java/com/dswork/myapp/ui/theme/DsTokens.kt" },
  "colors": { "background": "bg", "card": "surface", "accent": "accent" },
  "literals": {}
}
```

2. 跑 `gen.py`，新 app 的令牌文件就生成了。

`kind` 目前支持两种：

| kind | 适合 | 产物 |
|---|---|---|
| `android-xml` | Java/Kotlin + XML View | `colors.xml`（深/浅两套）+ `ds_dimens.xml` |
| `android-compose` | Kotlin + Compose | `DsTokens.kt`（DsPalette / DsRadius / DsSpace / DsType）|

## 颜色名怎么对上

令牌用的是**语义名**（`bg`、`surface`、`text_primary`、`inverted_surface`…），
各 app 有自己的历史命名（ChinGlish 叫 `muted`，List 叫 `textSecondary`）。
`apps.json` 的 `colors` 字段负责翻译：

```json
"colors": { "muted": "text_secondary" }
```

`@` 开头表示别名，指向另一个令牌，避免重复定义：

```json
"green": "@accent"
```

app 独有的、不在设计令牌里的颜色，写进 `literals`，同样受生成器管理。

## 当前接入状态

| app | 技术栈 | 接入方式 |
|---|---|---|
| ChinGlish | Java + XML | `app/res/values/colors.xml` + `values-night` 由生成器全量接管 |
| List (ToDoList) | Kotlin + Compose | `DsTokens.kt` 生成，`Theme.kt` 只做 Material3 映射 |
| Inter | Kotlin + Compose | `DsTokens.kt` 生成，`Theme.kt` 只做 Material3 映射；坐标网格等独有色进 `literals` |

## 应用内更新（Inter）

Inter 从 v1.2.1 起支持应用内检查更新。更新源是 GitHub Release 里的 `update.json`（失败回退 GitHub API），
APK 与 `update.json` 由 `Inter/tools/release.py` 上传，会校验 SHA-256、包名、版本号和签名。

发布步骤：

1. 改 `Inter/app/build.gradle.kts` 的 `versionCode` / `versionName`。
2. `cd D:\.dswork\App\Inter` 后执行 `.\gradlew.bat :app:assembleRelease --offline`。
3. 把 APK 复制到 `dist\Inter-v<版本>.apk`。
4. `python D:/.dswork/App/suite/tools/sync-all.py` 推代码。
5. `python D:/.dswork/App/Inter/tools/release.py --version <版本> --version-code <代码> --apk dist/Inter-v<版本>.apk --notes-file RELEASE_NOTES.md` 发 Release。

签名材料（`keystore/`、`keystore.properties`）只在本地，`publish.py` 和 `.gitignore` 都会拦住。

## 注意

- 生成的文件开头都有 `GENERATED FILE - DO NOT EDIT`，手改会被下一次生成覆盖。
- 要改颜色请改 `tokens.json`，不要改 app 里的资源文件。
- 三个 app 的构建方式不同（Gradle / 手写 aapt2），但都只是读这些生成文件，互不影响。

---

## 许可证

本项目采用 [GNU General Public License v3.0](LICENSE)（GPL-3.0）。

Copyright (C) 2026 ssyPromax

你可以自由使用、修改和分发本项目的代码；如果你分发修改后的版本，
必须以同样的 GPL-3.0 协议公开源代码。
