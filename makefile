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

export:
	pip freeze > requirements.txt
