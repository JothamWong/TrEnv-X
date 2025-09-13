.PHONY: build-ci
build-ci:
	# ci means code interpreter here
	docker build -t jialianghuang/default-code-interpreter:latest \
		--network host -f ci.Dockerfile .
		# for network proxy
		# --build-arg HTTP_PROXY=http://127.0.0.1:7890 \
		# --build-arg HTTPS_PROXY=http://127.0.0.1:7890

.PHONY: build-metagpt
build-metagpt:
	docker build -t jialianghuang/metagpt-sandbox:latest \
		--network host  -f metagpt.Dockerfile .

.PHONY: build-default
build-default:
	docker build -t jialianghuang/default-sandbox:latest \
		--network host  -f default.Dockerfile .

.PHONY: build-agent
build-agent:
	docker build -t jialianghuang/default-agent:latest \
		--network host  -f agent.Dockerfile .

.PHONY: build-owl
build-owl:
	docker build -t jialianghuang/default-owl:latest \
		--network host  -f owl.Dockerfile .

.PHONY: build-claude-code
build-claude-code:
	docker build -t jialianghuang/claude-code:latest \
		--network host \
		--build-arg RELEASE_TAG=openvscode-server-v1.101.2 \
		-f claude-code.Dockerfile .
