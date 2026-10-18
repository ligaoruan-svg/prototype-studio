.PHONY: install dev web test build mac clean

install:  ## 安装后端依赖（可编辑安装）
	python3 -m pip install -e .

dev:  ## 启动本地服务，浏览器打开 http://127.0.0.1:5173
	python3 -m uvicorn backend.server:app --host 127.0.0.1 --port 5173 --reload

web:  ## 前端开发服务器（后端需另开一个终端跑 8900 端口）
	cd frontend && npm run dev

test:  ## 跑后端和前端单元测试
	python3 -m unittest discover -s backend/tests -t .
	cd frontend && npm test

build:  ## 重新构建前端 dist
	cd frontend && npm run build

mac:  ## 打 Mac 安装包到 release/（Windows 版见 README「自己打包」）
	bash scripts/打包Mac应用.command

clean:  ## 清掉编译缓存
	find . -name __pycache__ -type d -not -path "./.venv/*" -exec rm -rf {} +
