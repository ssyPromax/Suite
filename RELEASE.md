# 双渠道发布说明

同一套源码，产出两个安装包：GitHub 直发版、应用商店版。两者**包名相同**，所以已装用户可以被商店接管更新。

## 为什么必须分成两个包

| 渠道 | 内置更新 | 原因 |
|---|---|---|
| GitHub | 保留 | 没有商店，只能自己检查 GitHub Releases |
| vivo 商店 | **关闭** | 审核规范 4.3.4：应用打开后提示更新版本会被驳回 |

代码里用编译期开关控制，不是运行期隐藏：商店包里那段逻辑根本不会被执行，界面上也没有「检查更新」入口。

## 构建命令

### List（ToDoList，Gradle）

```bash
cd D:\.dswork\App\ToDoList

# GitHub 渠道（默认）
./gradlew :app:assembleRelease -x lintVitalRelease

# 商店渠道
./gradlew :app:assembleRelease -Pchannel=store -x lintVitalRelease
```

> `-x lintVitalRelease` 是必须的：本机网络下 lint 会卡在联网检查上，跳过它不影响产物。
> 构建后产物在 `app\build\outputs\apk\release\app-release.apk`，两种渠道同名，
> 所以构建完请立刻另存（建议 `dist\List-GitHub-<版本>.apk` / `dist\List-Store-<版本>.apk`），
> 否则第二次构建会覆盖第一次。

开关对应 `BuildConfig.SELF_UPDATE`：
- `github` → true
- `store` → false

源码里三处受它控制：`MainActivity`（启动时的检查）、`UpdateNotifier.checkAndNotify`（后台检查总闸）、`AboutDialog`（检查更新按钮）、`BootReceiver`（开机重排闹钟）。

### ChinGlish（手写构建）

```bash
# GitHub 渠道
powershell -ExecutionPolicy Bypass -File D:\.dswork\App\ChinGlish\tools\build_apk.ps1

# 商店渠道
powershell -ExecutionPolicy Bypass -File D:\.dswork\App\ChinGlish\tools\build_apk.ps1 -Store
```

产物：
- GitHub：`dist\chinglish-<版本>.apk`
- 商店：`dist\chinglish-<版本>-store.apk`

脚本会在 `build\gen-src\` 生成 `BuildFlags.java`，`SELF_UPDATE = false` 时：
- 关于对话框不再显示「检查更新」
- 启动与后台的静默检查直接返回

## 签名（最重要的一件事）

两个渠道**必须用同一把签名**，否则商店版装不到已有用户机上，用户只能卸载重装（数据全丢）。

| App | 签名的文件 | 状态 |
|---|---|---|
| List | `keystore\list-release.jks` + `keystore.properties` | 新建，**必须备份** |
| ChinGlish | `tools\ciwen.keystore` | 沿用原有，勿替换 |

两个文件都已在 `.gitignore` 里，不会上传。请各自备份三份（U 盘 / 网盘 / 另一台机器）。
**密钥丢失 = 永远无法给已安装用户发更新**，只能换包名重新上架。

List 换了新签名，之前从 GitHub 装的旧版（调试签名）不能直接覆盖安装，老用户需要卸载一次再装新版。这个代价只发生一次。

## 发布前检查表

- [ ] `versionCode` 已递增（商店按它判断新旧，必须比线上大）
- [ ] 用商店渠道构建，启动后「关于」里没有「检查更新」
- [ ] APK 签名是正式证书：`apksigner verify --print-certs <apk>`
- [ ] 版本号、应用名与备案/软著一致
- [ ] 上传的是商店版，不是 GitHub 版

## vivo 上架前置条件

| 材料 | 周期 |
|---|---|
| 计算机软件著作权登记证书 | 40–60 工作日 |
| APP 备案号（工信部） | 约 22 工作日 |
| 应用名称与备案/软著一致 | — |

没有备案号，国内商店一律不予受理，建议先办证。