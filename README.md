# 校园宠物关爱与流浪动物服务平台

## 运行方式（本地）
```bash
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

## 功能验证（自动化）
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

## Docker 容器化部署

### 使用 Docker Compose（推荐）
```bash
docker compose up -d --build
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
docker build -t campus-pet-service:latest .
docker run -d --name campus-pet-service -p 8000:8000 \
  -e CAMPUS_DB_PATH=/data/campus_pet.db \
  -e CAMPUS_ADMIN_USER=admin \
  -e CAMPUS_ADMIN_PASSWORD=admin123456 \
  -v ${PWD}/data:/data \
  campus-pet-service:latest
```
