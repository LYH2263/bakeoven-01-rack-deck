# BakeOven

烘焙占炉排程：发酵+烘烤半开区间占用炉位，冲突检测与下一可开工窗口。

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
- `/ovens` — 炉位
- `/batches` — 批次
- `/gantt` — 甘特
- `/conflicts` — 冲突
- `/windows` — 可开工

## 使用说明

1. 查看产品配方时长与炉位。
2. 在炉位页为每座炉登记**醒发架格数**与**炉膛盘数**（可留空）。
3. 创建生产批次，系统按半开区间占炉并检测冲突：发酵段只占醒发架、烘烤段只占炉膛；架上发酵段超架格或膛上烘烤段超盘数即拒绝。两项上限都留空时只按时间重叠拒绝（端点相接不算同时）。
4. 甘特查看各炉重叠处当时的架/膛占用（超限标红）；冲突页写明“架满/膛满”及对手批次；可开工窗口辅助排产。

## 开发与测试

```bash
docker compose exec api pytest -q
```
