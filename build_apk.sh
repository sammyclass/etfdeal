#!/usr/bin/env bash
# 本地/Linux 一键编译 debug APK。首次运行会下载 Android SDK 和 NDK（约 4~5 GB），耗时 30~60 分钟。
set -euo pipefail
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk zip unzip python3-pip \
     autoconf automake libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
     libtinfo6 cmake libffi-dev libssl-dev
python3 -m pip install --upgrade buildozer cython
buildozer android debug
echo "完成：$(ls bin/*.apk)"
