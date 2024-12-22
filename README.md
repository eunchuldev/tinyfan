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

```python

from tinyfan import GcsStore, Flow
import os

# Build time configs:
# Pod configs are settled on the build time.
image = os.environ["IMAGE_NAME"]

# Runtime Configs:
# Other configs are revisited on runetime.
some_secret = os.environ[""]

# Flow is refer to the Argo Workflow Object.
# Flow configs are applied to all of child assets
flow = Flow(
    name="flow",
    image=os.environ["IMAGE_NAME"],
    envSecrets=[""],
    envConfigMaps=[""],
    as_default=True,
)
image = os.environ['IMAGE_NAME'],
sa_name = os.environ['SERVICE_ACCOUNT_NAME'],
gcs_store = GcsStore(),
naive_store = NaiveStore()

flow = Flow(
    store=naive_store,
)
# authorized by workload-identity-federation

@asset(
    schedule = "*/10 * * * *",
    image = "python3:alpine",
    store = NaiveStore(),
)
def target() -> str:
    return "world"


@asset(
    schedule = "*/10 * * * *",
    image = "python3:alpine",
    store = GcsStore(),
)
def target() -> str:
    return "world"

```


# License

This project is licensed under the MIT License.
