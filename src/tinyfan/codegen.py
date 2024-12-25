from tinyfan.flow import Flow, Asset, FLOW_CATALOG, DEFAULT_IMAGE
import importlib.util
from typing import Self
from .utils.yaml import dump as yaml_dump, dump_all as yaml_dump_all
from .utils.exjson import DATETIME_ANNOTATION
import inspect
import sys
import re
import json
import os
import pkgutil
import datetime
import croniter
from .argo_typing import ScriptTemplate
from .utils.embed import embed
from .utils.merge import deepmerge

VALID_CRON_REGEXP = r"^(?:(?:(?:(?:\d+,)+\d+|(?:\d+(?:\/|-|#)\d+)|\d+L?|\*(?:\/\d+)?|L(?:-\d+)?|\?|[A-Z]{3}(?:-[A-Z]{3})?) ?){5,7})|(@hourly|@daily|@midnight|@weekly|@monthly|@yearly|@annually)$"
VALID_DEPENDS_REGEXP = r"^(?!.*\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+)(?!.*\.(?!Succeeded|Failed|Errored|Skipped|Omitted|Daemoned)\w+)(?!.*(?:&&|\|\|)\s*(?:&&|\|\|))(?!.*!!)[A-Za-z0-9_&|!().\s]+$"

EXTRACT_DEPENDS_REGEXP = r"(?<!\.)\b([A-Za-z0-9_]+)\b"

RUNDATA_FILE_PATH = "/tmp/tinyfan/rundata.json"


def brackets_balanced(code: str) -> bool:
    code = re.sub(r"[^()]", "", code)
    while "()" in code:
        code = code.replace("()", "")
    return code == ""


def get_root_path(func):
    filename = inspect.getfile(func)
    path = os.path.abspath(os.path.dirname(filename))
    if not os.path.exists(os.path.join(path, "__init__.py")):
        return filename
    while os.path.exists(os.path.join(os.path.dirname(path), "__init__.py")):
        path = os.path.dirname(path)
    return path


def encode_schedule_to_k8sname(tz: str, cron: str) -> str:
    return f"{tz}|{cron}".lower().translate(str.maketrans("* ,-/_+|", "a-cds-p-", "@"))[:58]


def import_all_submodules(location: str):
    try:
        package = importlib.import_module(location)
    except ModuleNotFoundError:
        if not location.endswith(".py"):
            pkg_name = os.path.dirname(location)
            location = os.path.join(location, "__init__.py")
        else:
            pkg_name = "__tinyfan_repo__"
        spec = importlib.util.spec_from_file_location(pkg_name, location)
        if spec is None or spec.loader is None:
            raise ValueError(f"fail to load module from `{location}.`")
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
    if package.__name__ != "__tinyfan_repo__":
        for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            importlib.import_module(name)


class AssetNode:
    asset: Asset
    children: list[Self]
    parents: list[Self]

    def __init__(self, asset):
        self.asset = asset
        self.children = []
        self.parents = []

    def __hash__(self):
        return hash(self.asset.name)

    def asset_module_name(self):
        mod = inspect.getmodule(self.asset.func)
        return mod.__name__ if mod else None

    def rundatatmpl(self, schedule: str):
        cron = croniter.croniter(schedule, datetime.datetime.now())
        t1 = cron.get_next(datetime.datetime)
        t2 = cron.get_next(datetime.datetime)
        duration_sec = (t2 - t1).total_seconds()
        return re.sub(
            r'"(\{\{tasks\.[^.]+\.outputs\.parameters\.rundata\}\})"',
            r"\1",
            json.dumps(
                {
                    "ds": "{{=sprig.date('2006-01-02', workflow.scheduledTime)}}",
                    "ts": "{{workflow.scheduledTime}}",
                    "data_interval_start": {
                        DATETIME_ANNOTATION: "{{workflow.scheduledTime}}",
                    },
                    "data_interval_end": {
                        DATETIME_ANNOTATION: "{{=sprig.dateModify('%ss', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))}}"
                        % duration_sec,
                    },
                    "parents": {
                        p.asset.name: "{{tasks.%s.outputs.parameters.rundata}}" % p.asset.name for p in self.parents
                    },
                    "asset_name": self.asset.name,
                    "flow_name": self.asset.flow.name,
                    "module_name": self.asset_module_name(),
                }
            ),
        )

    def relatives(self, result: set[Self] | None = None) -> set[Self]:
        if result is None:
            result = set[Self]([self])
        for o in self.parents + self.children:
            if o not in result:
                result.add(o)
                o.relatives(result)
        return result


class AssetTree:
    flow: Flow
    nodes: dict[str, AssetNode]

    def __init__(self, flow: Flow):
        self.flow = flow
        self.nodes = {name: AssetNode(asset) for name, asset in flow.assets.items()}
        for node in self.nodes.values():
            sigs = inspect.signature(node.asset.func)
            func_param_names = list(sigs.parameters.keys())
            params_ids = set(name for name in func_param_names if name in self.flow.assets)

            if node.asset.depends is not None:
                depends_ids = set(re.findall(EXTRACT_DEPENDS_REGEXP, node.asset.depends))
                node.parents = [self.nodes[n] for n in depends_ids.union(params_ids)]
                node.asset.depends = f"({node.asset.depends}) && {' && '.join(params_ids - depends_ids)}".replace(
                    "_", "-"
                )
                for p in node.parents:
                    p.children.append(node)
            else:
                node.parents = [self.nodes[n] for n in params_ids]
                for p in node.parents:
                    p.children.append(node)
                node.asset.depends = " && ".join(params_ids).replace("_", "-")

    def compile(
        self,
        embedded: bool = True,
        container: ScriptTemplate = {},
    ) -> str:
        if len(self.nodes) == 0:
            return ""

        if embedded:
            source = embed("tinyfan", excludes=["codegen.py", "utils/embed.py", "**/__pycache__/*"], minify=False)
            root_location = get_root_path(list(self.nodes.values())[0].asset.func)
            source += embed(root_location)
            if not root_location.endswith(".py"):
                source += "from {{inputs.parameters.module_name}}" " import {{inputs.parameters.asset_name}}\n"
            source += "asset = {{inputs.parameters.asset_name}}.asset\n"
        else:
            source = (
                "from {{inputs.parameters.module_name}}"
                " import {{inputs.parameters.asset_name}}\n"
                "asset = {{inputs.parameters.asset_name}}.asset\n"
            )
        source += (
            "import os\n"
            "from tinyfan.utils.exjson import dumps, loads\n"
            "_, rundata = asset.run(loads('''{{inputs.parameters.rundata}}'''))\n"
            f"path = '{RUNDATA_FILE_PATH}'\n"
            "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
            "with open(path, 'w') as f:\n"
            "    f.write(dumps(rundata))\n"
        )

        relatives_by_schedules: dict[tuple[str, str], set[AssetNode]] = {}
        for node in self.nodes.values():
            if node.asset.schedule is None:
                continue
            schedule = (node.asset.tz or self.flow.tz, node.asset.schedule)
            if schedule not in relatives_by_schedules:
                relatives_by_schedules[schedule] = set()
            for o in node.relatives():
                relatives_by_schedules[schedule].add(o)

        manifests = [
            {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "CronWorkflow",
                "metadata": {
                    "name": f"""{self.flow.name}-{ encode_schedule_to_k8sname(tz, schedule) }""",
                    "generateName": f"""{self.flow.name}-{ encode_schedule_to_k8sname(tz, schedule) }-""",
                },
                "spec": {
                    "schedule": schedule,
                    "timezone": tz,
                    "workflowSpec": {
                        "entrypoint": "flow",
                        "podSpecPatch": yaml_dump(
                            {
                                "containers": [
                                    deepmerge(
                                        {
                                            "name": "main",
                                            "env": [
                                                {
                                                    "name": "TINYFAN_SOURCE",
                                                    "value": source,
                                                }
                                            ],
                                        },
                                        container or {},
                                        self.flow.container or {},
                                    )
                                ]
                            }
                        ),
                        "templates": [
                            {
                                "name": node.asset.name.replace("_", "-"),
                                "script": deepmerge(
                                    {
                                        "image": DEFAULT_IMAGE,
                                        "command": ["python"],
                                        "source": """import os;exec(os.environ['TINYFAN_SOURCE'])""",
                                    },
                                    container or {},
                                    self.flow.container or {},
                                    node.asset.container or {},
                                ),
                                "podSpecPatch": yaml_dump(
                                    {
                                        "containers": [
                                            deepmerge(
                                                {
                                                    "name": "main",
                                                },
                                                node.asset.container or {},
                                            )
                                        ]
                                    }
                                ),
                                "synchronization": {"mutexes": [{"name": f"{self.flow.name}-{node.asset.name}"}]},
                                "inputs": {
                                    "parameters": [
                                        {
                                            "name": "rundata",
                                            "value": "{{= nil }}",
                                        },
                                        {
                                            "name": "asset_name",
                                            "value": "{{= nil }}",
                                        },
                                        {
                                            "name": "module_name",
                                            "value": "{{= nil }}",
                                        },
                                    ]
                                },
                                "outputs": {
                                    "parameters": [
                                        {
                                            "name": "rundata",
                                            "valueFrom": {
                                                "path": RUNDATA_FILE_PATH,
                                            },
                                        }
                                    ],
                                },
                            }
                            for node in relatives
                        ]
                        + [
                            {
                                "name": "flow",
                                "dag": {
                                    "tasks": [
                                        {
                                            "name": node.asset.name.replace("_", "-"),
                                            "depends": node.asset.depends.replace("_", "-")
                                            if node.asset.depends is not None
                                            else None,
                                            "template": node.asset.name.replace("_", "-"),
                                            "arguments": {
                                                "parameters": [
                                                    {
                                                        "name": "rundata",
                                                        "value": node.rundatatmpl(schedule),
                                                    },
                                                    {
                                                        "name": "asset_name",
                                                        "value": node.asset.name,
                                                    },
                                                    {
                                                        "name": "module_name",
                                                        "value": node.asset_module_name(),
                                                    },
                                                ]
                                            },
                                        }
                                        for node in relatives
                                    ]
                                },
                            },
                        ],
                    },
                },
            }
            for (tz, schedule), relatives in relatives_by_schedules.items()
        ]
        return yaml_dump_all(manifests)


def codegen(
    location: str | None = None,
    embedded: bool = False,
    container: ScriptTemplate = {},
) -> str:
    """Generate argocd workflow resource as yaml from tinyfan definitions"""
    if location:
        import_all_submodules(location)
    return "\n---\n".join(AssetTree(flow).compile(embedded, container) for flow in FLOW_CATALOG.values())
