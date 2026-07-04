# BoardFlow

流程化看板项目，参考 [领歌 lg.team](https://www.lg.team/kanban/board_list) 的看板交互，用于管理项目流程、列表和卡片。

## 功能

- 看板列表：创建、编辑、删除看板
- 看板视图：多列表 Kanban 布局，支持卡片拖拽、列表排序
- 卡片类型：用户故事、任务、缺陷（带颜色标识）
- 卡片详情：描述、检查清单、评论
- 全局搜索：搜索看板与卡片
- 优先 Redis 存储，未配置时回退本地 JSON

## 技术栈

与 `tools_102BossHireTag` 保持一致：

- Python 3
- Flask
- Redis（可选）
- Bootstrap 5
- SortableJS（拖拽）
- Vercel / GitHub Actions（可选部署）

## 项目结构

```text
BoardFlow/
├── app.py                      # Flask 入口
├── routes/                     # 页面与 API 路由
├── services/                   # 业务与存储
│   └── card_editors.py         # 编辑器注册表（canvas / mindmap / …）
├── static/
│   ├── js/
│   │   ├── main.js             # 看板主应用
│   │   └── card-editors.js     # 卡片编辑器入口与图标
│   └── apps/                   # 第三方编辑器构建产物（互相隔离）
│       ├── canvas/             # tldraw
│       └── mindmap/            # mind-elixir
├── frontend/                   # npm workspaces
│   ├── apps/canvas/            # 画布独立 Vite 工程
│   ├── apps/mindmap/           # 思维导图独立 Vite 工程
│   └── packages/editor-shell/  # 共享顶栏 / 自动保存 / API
├── scripts/build-frontends.*   # 一键构建全部编辑器
└── templates/
    ├── index.html
    └── editors/                # 编辑器壳页面
```

每个第三方库单独打包到 `static/apps/<name>/`，**不会**与看板主 JS 或其他编辑器冲突。

## 本地运行

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

构建前端编辑器（首次或修改 frontend 后）：

```bash
# Git Bash / Linux
./scripts/build-frontends.sh

# Windows PowerShell
./scripts/build-frontends.ps1
```

复制配置：

```bash
cp env.example .env
```

启动：

```bash
python app.py
```

打开：

```text
http://localhost:9213
```

或使用脚本（与参考项目相同）：

```bash
./restart.sh start
```

Windows 下可用 Git Bash 执行同一脚本。

## 路由

前端采用 Hash 路由，与领歌类似：

| 路由 | 说明 |
| --- | --- |
| `#/home/list` | 看板列表 |
| `#/board/<id>` | 看板详情 |

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/boards` | 看板列表 |
| `POST` | `/api/boards` | 创建看板 |
| `GET` | `/api/boards/<id>` | 看板详情（含列表和卡片） |
| `PATCH` | `/api/boards/<id>` | 更新看板 |
| `DELETE` | `/api/boards/<id>` | 删除看板 |
| `POST` | `/api/boards/<id>/lists` | 创建列表 |
| `PATCH` | `/api/boards/<id>/lists/<list_id>` | 更新列表 |
| `DELETE` | `/api/boards/<id>/lists/<list_id>` | 删除列表 |
| `POST` | `/api/boards/<id>/lists/reorder` | 列表排序 |
| `POST` | `/api/boards/<id>/lists/<list_id>/cards` | 创建卡片 |
| `PATCH` | `/api/boards/<id>/cards/<card_id>` | 更新卡片 |
| `DELETE` | `/api/boards/<id>/cards/<card_id>` | 删除卡片 |
| `POST` | `/api/boards/<id>/cards/<card_id>/move` | 移动卡片 |
| `POST` | `/api/boards/<id>/cards/<card_id>/comments` | 添加评论 |
| `GET/PUT` | `/api/boards/<id>/cards/<id>/canvas` | 画布数据 |
| `GET/PUT` | `/api/boards/<id>/cards/<id>/mindmap` | 思维导图数据 |
| `GET` | `/api/search?q=` | 搜索 |

## 存储

`STORAGE_BACKEND` 支持：

```text
auto  有 REDIS_URL 时用 Redis，否则用本地 JSON
redis 强制使用 Redis，未配置 REDIS_URL 会报错
json  强制使用本地 JSON
```

复制配置：

```bash
cp env.example .env
```

Redis 环境变量（与 `tools_102BossHireTag` 一致）：

```text
STORAGE_BACKEND=redis
REDIS_URL=redis://...
REDIS_KEY_PREFIX=jjob:boardflow:state
REDIS_SETTINGS_KEY=jjob:boardflow:settings
REDIS_TIMEOUT_SECONDS=5
```

Redis 键结构（`REDIS_KEY_PREFIX` 默认为 `jjob:boardflow:state`）：

| Redis 键 | 类型 | 内容 |
| --- | --- | --- |
| `{prefix}:boards` | Hash | field=看板 ID，value=看板 JSON |
| `{prefix}:lists` | Hash | field=列表 ID，value=列表 JSON |
| `{prefix}:cards` | Hash | field=卡片 ID，value=卡片 JSON |
| `{prefix}:meta` | Hash | 自增 ID 等元数据 |
| `REDIS_SETTINGS_KEY` | String | 卡片类型、看板状态等配置 JSON |

配置了 `REDIS_URL` 时，若 Redis 暂时不可用会自动回退到本地 `data/boards.json`。

本地数据文件：`data/boards.json`

首次启动会自动写入示例看板「Linux_ubuntu 学习」。

## 部署

参考 `tools_102BossHireTag` 的 Vercel + Git tag 发布流程，配置：

```text
REDIS_URL
REDIS_KEY_PREFIX=jjob:boardflow:state
REDIS_SETTINGS_KEY=jjob:boardflow:settings
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```

发布（CI 会自动构建 frontend 后再部署）：

```bash
git tag v1.0.0
git push origin v1.0.0
```

### 新增编辑器（表格 / 统计等）

1. 在 `services/card_editors.py` 注册配置
2. 在 `frontend/apps/<name>/` 新建独立 Vite 工程
3. 在 `frontend/package.json` 的 build 脚本中加入 workspace
4. 在 `static/js/card-editors.js` 增加 Tab 与图标
5. 运行 `./scripts/build-frontends.sh`
