# Tinyfan

Tinyfan: Minimalist Data Pipeline Kit - Generate Argo Workflows with Python

# Features

* Generate Argo Workflows manifests from Python data pipeline definitions.
* Ease of Use and highly extendable
* Intuitive data model abstraction: let Argo handle orchestration—we focus on the data.
* Argo Workflows is notably lightweight and powerful – and so are we!
* Enhanced DevOps Experience: easly testable, Cloud Native and GitOps-ready.

# Our Goal

* **Minimize mental overhead** when building data pipelines.

# Not Our Goal

* **Full-featured orchestration framework:** We don't aim to be a battery-powered, comprehensive data pipeline orchestration solution.  
  No databases, web servers, or controllers—just a data pipeline compiler. Let's Algo Workflows handle all the complexity.

# Installation

```
# Requires Python 3.10+
pipx install tinyfan
```

# Tiny Example

```python
# main.py

# Asset definitions

from tinyfan import asset

@asset(schedule="*/3 * * * *")
def world() -> str:
    return "world"

@asset()
def greeting(world: str):
    print("hello " + world)
```

```shell
# Apply the changes to argo workflow

tinyfan template main.py | kubectl apply -f -
```

# Real World Example (still tiny though!)

Comming soon



# License

This project is licensed under the MIT License.
