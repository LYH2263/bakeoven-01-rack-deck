# BakeOven

烘焙占炉排程：醒发架与炉膛分开计容。批次发酵段只占醒发架、烘烤段只占炉膛，均按半开区间 `[start, end)` 占用（端点相接不算同时）。每座炉可登记醒发架格数与炉膛盘数；同一时刻架上发酵段数超过架格、或膛上烘烤段数超过盘数即拒绝排入。两项上限都留空时，只按时间重叠拒绝。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4500 |
| API | http://localhost:9500 |
| API 文档 | http://localhost:9500/docs |
| Postgres | localhost:5446 |

健康检查：`GET http://localhost:9500/api/health`

## 页面

- `/products` — 产品
- `/ovens` — 炉位（可设置醒发架格数 / 炉膛盘数，留空表示不限）
- `/batches` — 批次
- `/gantt` — 甘特（轨道下方标注各时段架/膛占用）
- `/conflicts` — 冲突（写明架满还是膛满，并列出对手批次）
- `/windows` — 可开工

## 使用说明

1. 查看产品配方时长与炉位。
2. 在炉位页设置醒发架格数与炉膛盘数（如一层 1 号炉为架 2、膛 1）。
3. 创建生产批次：发酵重叠但架未满可同炉，烘烤重叠且膛满则后一批被拒绝。
4. 甘特查看架/膛占用；冲突与可开工窗口辅助排产。

## 开发与测试

```bash
docker compose exec api pytest -q
```
