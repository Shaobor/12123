#!/bin/bash

# 创建 GitHub Release 脚本
# 使用方法: GITHUB_TOKEN=your_token ./create_release.sh

if [ -z "$GITHUB_TOKEN" ]; then
    echo "错误: 请设置 GITHUB_TOKEN 环境变量"
    echo ""
    echo "获取 Token 的方法:"
    echo "1. 访问 https://github.com/settings/tokens"
    echo "2. 点击 'Generate new token (classic)'"
    echo "3. 选择 'repo' 权限"
    echo "4. 生成并复制 token"
    echo ""
    echo "然后运行:"
    echo "  export GITHUB_TOKEN=your_token_here"
    echo "  ./create_release.sh"
    exit 1
fi

curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/758639304/12123/releases \
  -d @release_data.json

echo ""
echo "Release 创建完成！"





