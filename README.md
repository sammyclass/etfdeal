# ETF 溢价监控 · 安卓 App

把 `ETFdeal.py` 的「近 100 交易日溢价」部分重构成手机端 App：**Kivy 界面 + 自绘曲线**，
刻意不用 pandas / matplotlib / numpy，APK 体积小、编译快，也不会因为移动端缺 wheel 而编不过。

## 一、这个 App 能干什么

| 功能 | 说明 |
|---|---|
| 溢价曲线 | 近 100 交易日（可切近 20 日），按「美股QDII / 港股中概 / 黄金商品 / 债券货币 / A股ETF」分色 |
| 3% 告警线 | 图上红色虚线，一眼看出谁在持续溢价 |
| 最新榜单 | 每只标的「自己最新一天」的溢价、收盘价、单位净值（QDII 净值晚一天也照样显示） |
| 分组筛选 | 点顶部按钮只看某一类，避免 19 条线挤在一起 |
| 离线缓存 | 拉过一次后存本地 JSON，断网也能看上次结果 |
| 打开即刷新 | 安卓 8+ 限制后台常驻，所以不做后台服务：每次打开自动更新（缓存超 3 天强制重拉） |

数据口径与脚本一致：**溢价率 =（不复权收盘价 − 单位净值）/ 单位净值 × 100%**，
价格用东财日 K（`fqt=0`，东财→新浪→腾讯 三源回退），净值用东财 `f10/lsjz` 翻页取，
两者都**不复权**，除息日同步下台阶，曲线才连续。货币 ETF（511990）按百份计价，自动跳过。

## 二、和桌面版的分工

- 桌面 `ETFdeal.py`：**盘中逐分钟**采实时 IOPV、3% 弹窗/钉钉告警、收盘复盘——这是它的强项，继续用。
- 本 App：**日频看板**，随时掏出手机看「最近 100 天谁在溢价、溢价多少、有没有过 3%」。
  安卓对「锁屏后仍联网轮询」限制很严，硬做后台常驻会反复被杀，体验反而差，所以手机端只做日频。

## 三、怎么拿到 APK

### 方式 A（推荐，不用装 Android 环境）：GitHub Actions 云编译

1. 在 GitHub 新建一个**私有仓库**（空仓库即可）。
2. 把本目录下这些文件原样上传（网页拖拽也行）：
   ```
   main.py  etf_data.py  buildozer.spec
   assets/  .github/workflows/build-apk.yml
   ```
3. 进仓库的 **Actions** 页 → 左侧 `build-apk` → 右上 `Run workflow`。
4. 约 30~40 分钟后，本次运行页面底部的 **Artifacts** 里下载 `etf-premium-apk`，解开就是 `*.apk`。
5. 传到手机，允许「安装未知来源应用」，装完桌面就有图标。

> 首次编译要现下 Android SDK + NDK（约 4~5 GB），所以慢；之后再编会走缓存，几分钟就出包。

### 方式 B：本机 Linux / WSL2 编译

Windows 上开 WSL2（Ubuntu 22.04），把这几个文件拷进去，然后：

```bash
chmod +x build_apk.sh && ./build_apk.sh
```

脚本会自动装 JDK 17 和 buildozer，产物在 `bin/` 下（`etfpremium-1.0.0-*-debug.apk`）。
首次同样要下 SDK/NDK，机器建议 8 GB 内存以上。

### 方式 C：不想编译，直接跑 Python

安卓装 **Pydroid 3**，把桌面版 `ETFdeal.py` 拷进手机，用 pip 装 `requests pandas matplotlib`，
在 Pydroid 里直接运行。功能最全（含盘中实时），但不是 App 图标形态，也没法后台常驻。

## 四、改包名 / 改参数

`buildozer.spec`：

```ini
package.domain = com.doubao      # 改成你自己的域名倒写
package.name  = etfpremium
version       = 1.0.0
android.api   = 33               # 目标 SDK
android.minapi = 24              # 最低 Android 7.0
orientation   = portrait
```

`etf_data.py` 顶部：`THRESHOLD`（告警线，默认 3.0）、`DAYS`（默认取 100 天）、
`GROUPS`（分组与标的，增删代码即可）、`SKIP_CODES`（默认跳过 511990）。

## 五、已知限制

- 只做日频，不含盘中实时 IOPV；盘中盯盘用桌面版。
- QDII 的单位净值由基金公司次日披露，所以纳指/标普最新一天通常比 A 股 ETF 晚一天，
  榜单里已按「各自最新一天」显示，不会漏掉它们。
- 数据来自东方财富/新浪/腾讯公开接口，接口改版或限流时会自动回退/报错，重试即可。
- 本工具仅做数据统计展示，**不构成投资建议**；溢价高不等于能套利（QDII 申赎受限、净值时滞、流动性都会让实际成交偏离）。

## 六、目录

```
android_app/
├── main.py                 # Kivy 界面：曲线、分组筛选、榜单、缓存、刷新
├── etf_data.py             # 数据层：三源价格 + 净值翻页 + 对齐 + 缓存（纯 requests）
├── buildozer.spec          # 打包配置（图标、权限、架构、依赖）
├── build_apk.sh            # Linux/WSL 一键编译
├── .github/workflows/
│   └── build-apk.yml       # GitHub Actions 云编译，Actions 页点一下出 APK
└── assets/
    ├── icon.png            # 应用图标
    ├── presplash.png       # 启动图
    └── NotoSansSC-Regular.otf  # 中文字体子集（不打包中文会变方框）
```
