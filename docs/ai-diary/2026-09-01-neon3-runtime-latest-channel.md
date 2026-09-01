---
date: 2026-09-01
topic: SDK runtime 默认跟随最新 Neon3 release
type: implementation
status: completed
---

## 涉及的文件路径

- `packages/python-sdk/src/neon3_sdk/runtime.py`
- `packages/python-sdk/src/neon3_sdk/__init__.py`
- `packages/python-sdk/tests/test_client.py`
- `packages/node-sdk/src/runtime.ts`
- `packages/python-sdk/README.md`
- `packages/node-sdk/README.md`
- `README.md`
- `scripts/sync-neon3-stack.ps1`

## 发现的问题

- SDK 原来把 runtime release 固定为 `v0.2.1`，Neon3 每次更新都需要同步改 SDK 常量和缓存路径。
- 本地开发 checkout 已可通过 `NEON_ROOT` 使用，不应要求每个开发提交都创建 GitHub release。

## 采取的方案

- Python 和 Node SDK 默认 runtime 选择改为 `latest`。
- SDK 启动时访问 GitHub Releases API 的 `releases/latest`，解析 `tag_name`，按实际 tag 下载并缓存。
- 保留 `NEON3_RUNTIME_VERSION=v0.2.1` 之类的可复现固定版本开关。
- pipeline 的 runtime pin 检查同时接受 `latest` 和精确 release tag。

## 当前状态

已完成。默认行为自动跟随最新已发布 Neon3 release；未发布的本地 Neon3 commit 仍需 `NEON_ROOT` 指向本地 checkout，不能被 GitHub `latest` 自动发现。

## 测试与验证结果

- Python SDK：`python -m unittest discover -s tests -v`，9 passed。
- Node SDK：`npm test`，2 passed，TypeScript build passed。
- `git diff --check`：通过。
