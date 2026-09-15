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

tinyfan main.py | kubectl apply -f -
```

For a package, pass its directory or import name. Tinyfan statically discovers
modules containing `@asset`, so unrelated submodules are not executed during
manifest generation. Modules imported by an asset module (for example, a shared
`Flow` definition) are loaded normally.

```shell
tinyfan src/my_package
```

Automatic package discovery requires statically recognizable Tinyfan `@asset`
decorators. Dynamic asset registration and custom decorator wrappers are not
automatically discovered.

# Runtime metadata

Generated workflows read runtime metadata from the reserved `tinyfan-rundata`
input artifact at `/tmp/tinyfan/input.json`. Parent metadata is transported as
base64-encoded JSON, preserving datetime values and literal text through Argo
parameter substitution. Asset functions and store APIs still receive ordinary
Python values.

After upgrading, regenerate and apply all workflow manifests together. The
internal `rundata` output parameter now contains base64-encoded JSON, written to
`/tmp/tinyfan/rundata.b64`; it is not compatible with the previous plain JSON
transport. For packaged workflows, update the Tinyfan version in the container
image as well.

Intervals are calculated at runtime from the triggering workflow's cron schedule,
timezone, and `workflow.scheduledTime`. The interval runs from the previous
scheduled occurrence (inclusive) to the current one (exclusive), regardless of
task delays or retries. Month lengths and leap years are calendar-based; missing
DST times are skipped and repeated times are distinct occurrences.
`data_interval_start` and `data_interval_end` are timezone-aware datetimes in the
schedule's timezone. `ds` is the local start date and `ts` is its ISO timestamp
including the UTC offset. All tasks in a workflow use that workflow's interval.

Embedded workflows include croniter's required runtime modules and timezone data
for the configured zones; no runtime download is needed. Regenerate manifests
after timezone-data updates. Packaged images must install Tinyfan's dependencies,
including croniter 6.2.4 or newer and `tzdata`.

# Real World Example (still tiny though!)

Comming soon



# License

This project is licensed under the MIT License.
