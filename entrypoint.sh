#!/bin/bash

pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -U yt-dlp

# 运行Python程序 (启用Web界面，绑定到0.0.0.0以允许外部访问)
# "$@" 允许传递额外参数
python main.py --web --web-host 0.0.0.0 "$@" || true

# 保持容器运行
tail -f /dev/null 