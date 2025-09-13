.PHONY: install
install:
	poetry install --without=dev

grpc-gen:
	poetry run \
	python -m grpc_tools.protoc -I. --python_out=./sandbox_sdk/api --pyi_out=./sandbox_sdk/api --grpc_python_out=./sandbox_sdk/api ./orchestrator.proto
