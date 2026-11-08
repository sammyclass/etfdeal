[app]
title = ETF 溢价监控
package.name = etfpremium
package.domain = com.doubao

source.dir = .
source.include_exts = py,png,jpg,ttf,otf,json
source.exclude_patterns = cache,__pycache__,*.pyc,etf_premium_cache.json,*.zip,bin,.buildozer

# 依赖：只需 kivy + requests。刻意不引入 pandas / matplotlib / numpy，
# 曲线用 Kivy Graphics 自绘，APK 体积和编译时间都小很多。
requirements = python3,kivy,requests,urllib3,chardet,idna,certifi,openssl

version = 1.0.0
orientation = portrait
fullscreen = 0

# 图标 / 启动图
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png

# 安卓清单
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.presplash_color = #0E1A30

# 中文字体随包发布（assets/NotoSansSC-Regular.otf），否则安卓上中文会变方框
android.add_assets = assets/NotoSansSC-Regular.otf

[buildozer]
log_level = 2
warn_on_root = 1
