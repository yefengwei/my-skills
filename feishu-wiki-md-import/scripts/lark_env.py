# -*- coding: utf-8 -*-
r"""
lark-cli 导入飞书知识库的共享环境配置。

所有脚本从这里读取机器相关常量；每项都支持环境变量覆盖，默认值即作者本机配置。
换机器 / 换项目时优先用环境变量覆盖，不必改脚本。

环境变量一览（均可选）：
    LARK_MD_BASE     本地 Markdown 项目根目录       默认 D:\yefengwei\private\编程导航项目md
    LARK_ENTRY       lark-cli 入口 run.js 绝对路径   默认本机 cli-connector-packages 路径
    LARK_SPACE_ID    飞书知识库空间 ID                默认 7493948997678137346
    LARK_WIKI_PARENT 目标父节点 node_token            默认 计算机科学与技术/编程导航
    LARK_NODE_OPTIONS Node 预加载 shim                默认 WorkBuddy genie-safe-delete.cjs
    LARK_CHROME      绿色版 Chrome 绝对路径           默认 D:\software\Chrome\App\Chrome.exe
    LARK_CDP_PROFILE Chrome CDP user-data-dir         默认 D:\Downloads\.workbuddy\chrome-cdp-prof
    LARK_CDP_PORT    SVG 截图 CDP 端口                默认 9228
    LARK_NODE_BIN    node 可执行名                    默认 node
"""
import os


def _env(name, default):
    return os.environ.get(name) or default


BASE = _env('LARK_MD_BASE', r'D:\yefengwei\private\编程导航项目md')
LARK_ENTRY = _env('LARK_ENTRY',
                  r'C:\Users\ysq\.workbuddy\binaries\node\cli-connector-packages\node_modules'
                  r'\@larksuite\cli\scripts\run.js')
SPACE = _env('LARK_SPACE_ID', '7493948997678137346')
WIKI_PARENT = _env('LARK_WIKI_PARENT', 'L2Eqw2RTcicJYYkMsKucEgcDnXb')
NODE_OPTIONS = _env(
    'LARK_NODE_OPTIONS',
    '--require="D:/software/WorkBuddy/resources/app.asar.unpacked/cli/vendor/shim/genie-safe-delete.cjs"')
NODE_BIN = _env('LARK_NODE_BIN', 'node')
CHROME = _env('LARK_CHROME', r'D:\software\Chrome\App\Chrome.exe')
CDP_PROFILE = _env('LARK_CDP_PROFILE', r'D:\Downloads\.workbuddy\chrome-cdp-prof')
CDP_PORT = int(_env('LARK_CDP_PORT', '9228'))

# 每次 lark-cli 子进程都注入的干净环境（去掉 WorkBuddy 代理，避免 127.0.0.1:7890 拦截）
PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy')


def clean_env():
    env = dict(os.environ)
    env['NODE_OPTIONS'] = NODE_OPTIONS
    for k in PROXY_KEYS:
        env.pop(k, None)
    return env
