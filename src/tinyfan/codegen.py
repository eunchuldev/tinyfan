from tinyfan.flow import Flow, Asset, FLOW_REGISTER, DEFAULT_IMAGE
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
from .utils.merge import deepmerge, dropnone
from .config import CLI_CONFIG_STATE, Config, ConfigValue, ConfigMapKeyRef, ConfigMapRef, SecretKeyRef, SecretRef
from .flowrundata import FlowRunData

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
    refs: list[Config | ConfigValue | str | None]
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
        data_interval_start_tmpl = (
            f"sprig.dateModify('-{duration_sec}s', sprig.toDate('2006-01-02T15:04:05Z07:00', workflow.scheduledTime))"
        )
        return re.sub(
            r'"(\{\{tasks\.[^.]+\.outputs\.parameters\.rundata\}\})"',
            r"\1",
            json.dumps(
                {
                    "ds": "{{=sprig.date('2006-01-02', %s)}}" % data_interval_start_tmpl,
                    "ts": "{{=%s}}" % data_interval_start_tmpl,
                    "data_interval_start": {
                        DATETIME_ANNOTATION: "{{=%s}}" % data_interval_start_tmpl,
                    },
                    "data_interval_end": {
                        DATETIME_ANNOTATION: "{{workflow.scheduledTime}}",
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
            known_names = (
                set(self.flow.assets.keys())
                | set((self.flow.resources or {}).keys())
                | set((self.flow.configs or {}).keys())
                | set(inspect.get_annotations(FlowRunData).keys())
            )
            unknown_names = [n for n in func_param_names if n not in known_names]
            if len(unknown_names) > 0:
                raise Exception(
                    f"unknown asset args: {', '.join('`' + n + '`' for n in unknown_names)} from asset `{node.asset.name}`"
                )

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

            flow_resources = self.flow.resources or {}
            flow_refs = self.flow.configs or {}
            param_resources = [flow_resources[n] for n in func_param_names if n in flow_resources]
            resource_refs = [ref for res in param_resources for ref in res.get_refs()]
            param_refs = [flow_refs[n] for n in func_param_names if n in flow_refs]
            node.refs = list(set(resource_refs + param_refs))

    def relatives_by_schedules(self) -> dict[tuple[str, str], set[AssetNode]]:
        relatives_by_schedules: dict[tuple[str, str], set[AssetNode]] = {}
        for node in self.nodes.values():
            if node.asset.schedule is None:
                continue
            schedule = (node.asset.tz or self.flow.tz, node.asset.schedule)
            if schedule not in relatives_by_schedules:
                relatives_by_schedules[schedule] = set()
            for o in node.relatives():
                relatives_by_schedules[schedule].add(o)
        return relatives_by_schedules

    def dagviz(self) -> str | None:
        try:
            import networkx as nx
        except ImportError:
            return None

        from .dagviz import dagviz

        relatives_by_schedules = self.relatives_by_schedules()
        g: nx.DiGraph = nx.DiGraph()
        # g.add_node(self.flow.name)
        # g.add_nodes_from([k for k in relatives_by_schedules.keys()])
        # g.add_nodes_from(self.nodes.keys())
        for (_, schedule), relatives in relatives_by_schedules.items():
            g.add_edge(self.flow.name, schedule)
            g.add_edges_from([(schedule, r.asset.name) for r in relatives])
            g.add_edges_from([(r.asset.name, d.asset.name) for r in relatives for d in r.parents])
        return dagviz(g, round_angle=True)

    def compile(
        self,
        embedded: bool = True,
        container: ScriptTemplate = {},
        serviceAccountName: str | None = None,
    ) -> str:
        if len(self.nodes) == 0:
            return ""

        source = ""
        if embedded:
            source += embed("tinyfan", excludes=["codegen.py", "utils/embed.py", "**/__pycache__/*"], minify=False)
        source += (
            "from tinyfan.config import CLI_CONFIG_STATE\n"
            f"CLI_CONFIG_STATE.cli_args = {json.dumps(CLI_CONFIG_STATE.cli_args)}\n"
        )
        if embedded:
            root_location = get_root_path(list(self.nodes.values())[0].asset.func)
            source += embed(root_location)
            if not root_location.endswith(".py"):
                source += "from {{inputs.parameters.module_name}} import {{inputs.parameters.asset_name}}\n"
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

        relatives_by_schedules = self.relatives_by_schedules()

        manifests = [
            {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "CronWorkflow",
                "metadata": {
                    "name": f"""{self.flow.name}-{encode_schedule_to_k8sname(tz, schedule)}""",
                    "generateName": f"""{self.flow.name}-{encode_schedule_to_k8sname(tz, schedule)}-""",
                },
                "spec": {
                    "schedule": schedule,
                    "timezone": tz,
                    "workflowSpec": {
                        "entrypoint": "flow",
                        **dropnone({"serviceAccountName": serviceAccountName or self.flow.serviceAccountName}),
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
                                **dropnone({"serviceAccountName": node.asset.serviceAccountName}),
                                "script": deepmerge(
                                    {
                                        "image": DEFAULT_IMAGE,
                                        "command": ["python"],
                                        "source": """import os;exec(os.environ['TINYFAN_SOURCE'])""",
                                        "env": [
                                            {
                                                "name": ref._env_name(),
                                                "valueFrom": {
                                                    "configMapKeyRef": {
                                                        "name": ref.name,
                                                        "key": ref.key,
                                                    }
                                                },
                                            }
                                            for ref in node.refs
                                            if isinstance(ref, ConfigMapKeyRef)
                                        ]
                                        + [
                                            {
                                                "name": ref._env_name(),
                                                "valueFrom": {
                                                    "secretKeyRef": {
                                                        "name": ref.name,
                                                        "key": ref.key,
                                                    }
                                                },
                                            }
                                            for ref in node.refs
                                            if isinstance(ref, SecretKeyRef)
                                        ],
                                        "envFrom": [
                                            {
                                                "configMapRef": {
                                                    "name": ref.name,
                                                }
                                            }
                                            for ref in node.refs
                                            if isinstance(ref, ConfigMapRef)
                                        ]
                                        + [
                                            {
                                                "secretRef": {
                                                    "name": ref.name,
                                                }
                                            }
                                            for ref in node.refs
                                            if isinstance(ref, SecretRef)
                                        ],
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
        manifest = ""
        dagviz = self.dagviz()
        if dagviz:
            manifest += "# " + dagviz.replace("\n", "\n# ") + "\n\n"
        manifest += yaml_dump_all(manifests)
        return manifest


def codegen(
    flow: Flow | None = None,
    location: str | None = None,
    embedded: bool = False,
    container: ScriptTemplate = {},
    serviceAccountName: str | None = None,
) -> str:
    """Generate argocd workflow resource as yaml from tinyfan definitions"""
    CLI_CONFIG_STATE.codegen = True
    if flow:
        result = AssetTree(flow).compile(embedded, container, serviceAccountName)
    elif location:
        import_all_submodules(location)
        result = "\n---\n".join(
            AssetTree(flow).compile(embedded, container, serviceAccountName) for flow in FLOW_REGISTER.values()
        )
    else:
        result = "\n---\n".join(
            AssetTree(flow).compile(embedded, container, serviceAccountName) for flow in FLOW_REGISTER.values()
        )
    CLI_CONFIG_STATE.codegen = False
    return result
