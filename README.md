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

# Native Argo options

Use native Argo field names at the level where Argo defines them:

| Tinyfan option | Generated location | Examples |
| --- | --- | --- |
| `Flow(workflowSpec={...})` or `codegen(workflowSpec={...})` | `spec.workflowSpec` | `nodeSelector`, `tolerations`, `affinity`, `parallelism`, `templateDefaults` |
| `@asset(template={...})` | The asset's entry in `workflowSpec.templates` | `nodeSelector`, `tolerations`, `retryStrategy`, `timeout`, pod `metadata` |
| `@asset(task={...})` | The asset's DAG task | `when`, additional `arguments` |
| `container={...}` | The script container | `image`, `resources`, `env`, `volumeMounts` |

```python
from tinyfan import Flow, asset

flow = Flow(
    "batch",
    workflowSpec={
        "nodeSelector": {"nodepool": "batch"},
        "tolerations": [{"key": "batch", "operator": "Exists", "effect": "NoSchedule"}],
        "arguments": {"parameters": [{"name": "enabled", "value": "true"}]},
        "templateDefaults": {"retryStrategy": {"limit": "2"}},
    },
)

@asset(
    flow=flow,
    schedule="@daily",
    container={"image": "python:3.12"},
    template={"nodeSelector": {"nodepool": "high-memory"}, "timeout": "30m"},
    task={"when": "{{workflow.parameters.enabled}} == true"},
)
def report():
    return "ready"
```

These dictionaries pass native options through without a field whitelist, so
additional Argo options do not need new Tinyfan keyword arguments. They must be
valid for your installed Argo version; see the [Argo field reference](https://argo-workflows.readthedocs.io/en/latest/fields/).
Template and workflow scheduling inheritance follows Argo's rules. Tinyfan does
not move pod or task fields into the container.

`Flow.workflowSpec` overrides `codegen(workflowSpec=...)` defaults: dictionaries
merge recursively, while lists and scalar values are replaced, including empty
lists, `False`, and zero. Configuration dictionaries are not mutated. Explicit
`serviceAccountName` arguments take precedence over the corresponding native
option. Use `workflowSpec.templateDefaults` for defaults shared by asset templates.

Tinyfan rejects options that replace its generated wiring: workflow entrypoint,
templates and source pod patch; template identity, executable body, inputs,
outputs, source pod patch and mutex; and task identity, template and dependencies.
Use the existing `container`, `inputs`, `outputs`, and `depends` arguments for
those settings. `task.arguments` can add parameters and artifacts, but cannot
replace Tinyfan's reserved runtime parameters or input artifact. `continueOn` is incompatible with
Argo's enhanced `depends`; use a condition such as `depends="report.Failed"`.

`when` is an Argo expression and does not infer dependency edges. Declare upstream
assets through function arguments or `depends`; use Argo task names (underscores
become hyphens) inside expressions. A parent that did not succeed has empty
runtime metadata and supplies `None` as its stored value. To skip a consumer
unless its parent succeeded, use `depends="report.Succeeded"`.

These options require Tinyfan 0.5.1 or newer in both the compiler environment and
packaged workflow images. Regenerate manifests after upgrading.

# Embedded source

Embedded workflows unpack their source into temporary directories, so package
data works with both `importlib.resources` and paths relative to `__file__`.
Use `Path(__file__).parent` to locate data; the working directory is unchanged.

Regular packages include their files and subdirectories, including extensionless
data files. Embedding a nested module includes its top-level package. Standalone
scripts include their containing directory so sibling imports and data files are
available; keep scripts in a directory containing only files intended for the
workflow. Git metadata, `.venv`/`venv`, Python bytecode, and common tool caches are
excluded by default. Scripts execute as modules, preserving `__file__`, future
imports, and runtime annotations; `if __name__ == "__main__"` blocks do not run.

The embedding utilities accept `includes` and `excludes` glob patterns relative
to the bundled directory (the top-level package for nested modules). Excluding a
directory excludes its contents. Bundled imports take precedence over installed
copies that have not already been imported. Temporary files are cleaned up on
normal process exit, and unchanged source produces identical bundle bytes.

Embedding does not resolve third-party dependencies or copy distribution metadata
such as `.dist-info`. Install dependencies in the container image, including
packages that need native libraries or `importlib.metadata`. Import-name embedding
of a standalone module includes only its `.py` file; use a script path or regular
package for accompanying data. Native libraries and namespace-package import
names are rejected; use regular packages with `__init__.py`. Keep embedded source
and data small because generated workflows carry them in an environment variable.

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
timezone, and `workflow.scheduledTime`. If the workflow parameter `cronScheduleTime`
is present, it takes precedence, supporting the timestamp supplied by
`argo cron backfill` with its default `--argname`. Both RFC 3339 timestamps and the
alpha CLI's Go-style timestamps (for example, `2026-03-09 00:00:00 -0400 EDT`)
are accepted. Invalid or empty supplied values fail instead of falling back.
The interval runs from the previous
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

Backfill CLI compatibility is version-dependent: use a version supporting
`spec.schedules` and the configured timezone. Older alpha implementations, such
as Argo 3.7.0, only read the legacy `spec.schedule` field. Tinyfan does not add a
duplicate `cronScheduleTime` default argument because the CLI appends it itself.

# Real World Example (still tiny though!)

Comming soon



# License

This project is licensed under the MIT License.
