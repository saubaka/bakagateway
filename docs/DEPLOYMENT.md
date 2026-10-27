# 部署与维护

## 安装与配置

```bash
cp .env.production.example .env
# 按自己的受控域名修改配置；本机HTTP使用.env.example
python3 scripts/prepare_local.py
docker compose -p bakagateway up -d --build --wait
docker compose -p bakagateway ps
```

| 变量 | 作用 |
| --- | --- |
| BG_ENV | 本机HTTP用local，公开服务用production |
| BG_PUBLIC_URL | 固定公开源，也是OIDC issuer；生产必须HTTPS，不含路径/凭据/查询 |
| BG_ALLOWED_HOSTS | 受控主机名，逗号分隔；保留localhost/127.0.0.1用于容器健康检查 |
| BG_BIND_ADDRESS / BG_WEB_PORT | 默认回环127.0.0.1:5180，只有web暴露端口 |
| BG_SECRETS_DIR | 本实例独立秘密目录，默认.secrets |
| BG_IMAGE_PREFIX | 镜像名前缀，多个独立实例应分别设置 |

公开HTTPS由受控外层代理终结并保留原Host；内部web覆盖转发来源，API只信任内部一跳，不直接暴露api/db端口。经过外层代理时按来源IP限流可能由用户共享，部署者应核对代理策略。生产Cookie使用Secure/HttpOnly/SameSite=Lax。

三份秘密是app_key、db_password、db_admin_password。配置生成器不打印内容、不覆盖已有文件。父目录0700、文件0444以便非root容器只读挂载，父目录不能放宽。签名私钥在signing_keys卷中0600，API以独立普通用户运行。不要把这些值写进Git、镜像、日志、URL或前端变量。

启动先等待数据库健康，再串行迁移、初始化或复用签名密钥，最后启动API/web。初始化没有账号或接入应用，注册默认关闭。`/api/health/live`验证进程，`/api/health/ready`还验证数据库、迁移和签名。发生故障时检查健康与一次性任务，不删库代替修复。

## 账号、邮件与应用

```bash
docker compose -p bakagateway exec api flask --app app:create_app create-admin --username YOUR_NAME --email YOUR_EMAIL
docker compose -p bakagateway exec api flask --app app:create_app configure-mail --host SMTP_HOST --port 587 --sender SENDER_EMAIL --security starttls --username SMTP_USER
docker compose -p bakagateway exec api flask --app app:create_app mail-test --recipient YOUR_EMAIL
docker compose -p bakagateway exec api flask --app app:create_app registration on
```

密码由终端交互输入，创建首管表示维护者确认邮箱归属。邮件先验证连接再加密保存，生产SMTP必须TLS；原app_key丢失会导致配置不能解密。也可在登录后的管理后台配置和验证发信。

在后台登记真实应用、精确回跳与资料范围。平台会话和应用凭据独立；接入应用使用自己的后端保存客户端秘密和令牌。新建/轮换秘密只展示一次，关闭后不回取；账号安全变更、撤销和应用管理会使相关旧凭据失效。固定issuer不能随表单任意修改。

## 维护

```bash
python3 scripts/operations.py --project bakagateway status
python3 scripts/operations.py --project bakagateway maintenance
```

维护清除过期验证、会话、限流、协议记录和旧的无引用图片，保留有效账号、当前头像/图标与有效期内重放检测记录。由维护者安排一次串行调度，不在多个应用worker里各启一份。备份或升级时暂停外部维护和所有直接CLI写入；本机项目锁不能协调其他主机或直接Docker命令。

## 备份与全新恢复

安排短暂停写窗口，备份输出放在源码目录以外：

```bash
python3 scripts/operations.py --project bakagateway backup --output /secure-backups/bakagateway-YYYYMMDD-HHMM
```

工具停止web/api，把数据库custom格式、uploads、signing_keys和原三份秘密一起保存，并生成完整性清单，再恢复原服务。备份含身份数据和私钥，0700/0600不是加密，应由维护者的可信加密异机系统保存。SHA256只能检测损坏，不能证明来源可信。保留对应版本源码、镜像和非秘密配置。

只将可信备份恢复到**全新项目、默认私有卷和不存在的新秘密目录**，保持原issuer和备份对应镜像版本，不先生成替代秘密：

```bash
export BG_SECRETS_DIR=/srv/bakagateway-restore/secrets
export BG_WEB_PORT=5182
python3 scripts/operations.py --project bakagateway-restore restore --input /secure-backups/bakagateway-YYYYMMDD-HHMM
```

工具拒绝覆盖已有实例、损坏或越界归档，先恢复数据库普通角色和数据，再恢复文件/签名并健康启动。失败保留新目标供排查，不自动删除源数据。恢复后验证身份、会话、配置、图片、应用接入/刷新与签名；快照可能恢复当时有效的凭据，需按事故背景决定是否统一撤销。不要只恢复数据库或重新生成app_key。

## 升级与回退

先备份并保留旧镜像，停止外部写入；在原项目构建新版本并`up -d --wait`，串行迁移成功后才启动API，核对主要流程。迁移失败不要绕过依赖或删库。数据库未改变时可回到旧镜像；数据库已经变化时不能假设镜像回退等于数据回退，应使用匹配版本备份在全新目标恢复并验证后切换。正式数据不执行`down -v`。
