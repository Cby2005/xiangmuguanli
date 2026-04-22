# 校园宠物关爱与流浪动物服务平台

## 运行命令（本地）
```bash
# 启动服务
python main.py --host 127.0.0.1 --port 8000
```

访问地址：
- `http://127.0.0.1:8000/index.html`

默认管理员账号：
- 用户名：`admin`
- 密码：`admin123456`

可通过环境变量覆盖：
- `CAMPUS_ADMIN_USER`
- `CAMPUS_ADMIN_PASSWORD`

## 功能验证命令（自动化）
项目包含端到端接口验证脚本，覆盖核心流程：
- 宠物档案新增
- 领养申请提交流程
- 管理员登录与审核权限
- 救助工单状态推进
- 走失信息发布与找回
- 活动报名与重复报名拦截
- 物资捐助合法性校验

执行测试：
```bash
python -m unittest tests/test_feature_flow.py -v
```

## Docker 容器化部署命令

### 使用 Docker Compose（推荐）
```bash
# 构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f
```

服务端口：
- `8000`

数据库挂载：
- 主机目录 `./data` 映射到容器 `/data`
- 数据文件：`/data/campus_pet.db`

停止服务：
```bash
docker compose down
```

### 使用 Docker 命令
```bash
# 构建镜像
docker build -t campus-pet-service:latest .

# 运行容器
docker run -d --name campus-pet-service -p 8000:8000 \
  -e CAMPUS_DB_PATH=/data/campus_pet.db \
  -e CAMPUS_ADMIN_USER=admin \
  -e CAMPUS_ADMIN_PASSWORD=admin123456 \
  -v ${PWD}/data:/data \
  campus-pet-service:latest
```

## GitHub Actions 自动化流水线
已提供工作流文件：
- `.github/workflows/ci-docker.yml`

触发规则：
- Push 到 `main`
- PR 到 `main`
- 手动触发 `workflow_dispatch`

流水线内容：
1. 自动运行测试：`python -m unittest tests/test_feature_flow.py -v`
2. 测试通过后自动构建 Docker 镜像
3. 非 PR 事件自动推送镜像到 GHCR：
   - `ghcr.io/<owner>/<repo>:latest`
   - `ghcr.io/<owner>/<repo>:sha-<commit>`

拉取并运行 GHCR 镜像：
```bash
docker pull ghcr.io/cby2005/xiangmuguanli:latest
docker run -d --name campus-pet-service -p 8000:8000 \
  -e CAMPUS_DB_PATH=/data/campus_pet.db \
  -e CAMPUS_ADMIN_USER=admin \
  -e CAMPUS_ADMIN_PASSWORD=admin123456 \
  -v ${PWD}/data:/data \
  ghcr.io/cby2005/xiangmuguanli:latest
```
