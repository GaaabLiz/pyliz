# PYLIZ
This is a simple python library that contains some useful functions that I use in my projects.

## Installation
```bash
pip install pylizlib
```

## Description
The main class of this library is **PylizLib**. It's a class used for handle file and directories for a python script/project.

It allows you to:
- easily manage directories and files
- easily read and write a single configuration file

### Example

```python
from pylizlib import PylizLib

# Create an instance of PylizLib.
# This will create a directory with the name of your app in your home directory.
app = PylizLib("name_of_your_app") 

# Create a directory in the app directory.
app.add_folder("key_for_folder", "name_of_folder")

# Get the path directory.
path = app.get_folder_path("key_for_folder")

# create app ini file and get/set value
app.create_ini("medializ.ini", [])
app.set_ini_value("section", "key", "value")
value = app.get_ini_value("section", "key")
```