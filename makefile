install:
	pip install -r requirements.txt

run:
	python main.py

clean:
	rm -rf __pycache__
	rm -rf dist
	rm -rf build

build:
	pyinstaller main.py --onefile

package:
	python setup.py sdist bdist_wheel

export:
	pip freeze > requirements.txt

upload:
	twine upload dist/*

docs-gen:
	pdoc -o docs -d markdown pylizlib

sync:
	uv sync --all-extras