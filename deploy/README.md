# 服务器部署

要求 Docker Compose，域名指向服务器，80/443 可用。局域网需自行部署受访问设备信任的 HTTPS 证书。

1. 复制 `.env.example` 到 `.env`，填写 DOMAIN、ADMIN_PASSWORD、DASHSCOPE_API_KEY 与评分模型配置。
2. `QWEN_OMNI_WS_URL` 必须是供应商实时 WebSocket 端点，不是 OpenAI 兼容 HTTP 地址。账号必须有目标模型权限。评分服务使用 DEEPSEEK_* 兼容配置。
3. 执行 `docker compose --env-file .env up -d --build`。
4. 检查 `docker compose ps` 与 `docker compose logs --tail=100 app`。
5. `/api/health` 应显示数据库 up；匿名 `/api/sessions` 返回 401；管理员登录成功。
6. 使用专门测试候选人完成邀请→授权→面试→结束→报告流程，再交付。

数据库保存在 interview_data 卷。禁止在保留数据时运行 `down -v`。备份 SQLite 时停止 app，再复制数据库到独立备份存储，随后启动 app；恢复前保留原数据库，验证恢复后记录完整。升级前记录旧镜像 ID 并备份数据库，回滚代码不要覆盖新产生的记录。

Caddy 负责 TLS，应用负责管理员验证。不要将开发服务器直接暴露公网。管理员密码放在服务器 .env，不写入 Git。仅将经批准的客户数据迁移到新服务器；默认新建空数据库。

当前为单组织版本。多人权限、操作审计、备份自动化、数据删除/保留策略与公网访问限流，需要根据客户合同进一步配置。
