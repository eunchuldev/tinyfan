import ast
import copy
import importlib.util
import inspect
import json
import os
import re
import sys
import tokenize
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

import croniter

from tinyfan.flow import DEFAULT_IMAGE, FLOW_REGISTER, Asset, Flow

from .argo_typing import ScriptTemplate, TemplateInputs, TemplateOutputs
from .config import CLI_CONFIG_STATE, Config, ConfigMapKeyRef, ConfigMapRef, ConfigValue, SecretKeyRef, SecretRef
from .flowrundata import FlowRunData
from .utils.embed import embed
from .utils.merge import deepmerge, dropnone
from .utils.yaml import dump as yaml_dump
from .utils.yaml import dump_all as yaml_dump_all

VALID_CRON_REGEXP = r"^(?:(?:(?:(?:\d+,)+\d+|(?:\d+(?:\/|-|#)\d+)|\d+L?|\*(?:\/\d+)?|L(?:-\d+)?|\?|[A-Z]{3}(?:-[A-Z]{3})?) ?){5,7})|(@hourly|@daily|@midnight|@weekly|@monthly|@yearly|@annually)$"
VALID_DEPENDS_REGEXP = r"^(?!.*\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+)(?!.*\.(?!Succeeded|Failed|Errored|Skipped|Omitted|Daemoned)\w+)(?!.*(?:&&|\|\|)\s*(?:&&|\|\|))(?!.*!!)[A-Za-z0-9_&|!().\s]+$"

EXTRACT_DEPENDS_REGEXP = r"(?<!\.)\b([A-Za-z0-9_]+)\b"

RUNDATA_INPUT_FILE_PATH = "/tmp/tinyfan/input.json"
RUNDATA_FILE_PATH = "/tmp/tinyfan/rundata.b64"
INTERNAL_INPUT_PARAMETERS = {"rundata", "asset_name", "moduledata"}
INTERNAL_OUTPUT_PARAMETERS = {"rundata"}


def merge_template_io(
    template_io: dict, user_io: TemplateInputs | TemplateOutputs | None, reserved_parameter_names: set[str]
) -> dict:
    result = copy.deepcopy(template_io)
    if user_io is None:
        return result
    for key, value in user_io.items():
        if key in ("parameters", "artifacts"):
            if not isinstance(value, list):
                raise TypeError(f"asset {key} must be a list")
            reserved_names = (
                reserved_parameter_names
                if key == "parameters"
                else {artifact["name"] for artifact in template_io.get("artifacts", [])}
            )
            conflicts = [
                item.get("name") for item in value if isinstance(item, dict) and item.get("name") in reserved_names
            ]
            if conflicts:
                names = ", ".join(f"`{name}`" for name in conflicts)
                raise ValueError(f"asset {key} cannot redefine tinyfan internal {key}: {names}")
            result.setdefault(key, [])
            result[key].extend(copy.deepcopy(value))
        elif isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deepmerge(result[key], copy.deepcopy(value))
        else:
            result[key] = copy.deepcopy(value)
    return result


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


def _defines_tinyfan_asset(source_path: Path) -> bool:
    """Return whether a module has a statically recognizable Tinyfan asset."""
    with tokenize.open(source_path) as source_file:
        tree = ast.parse(source_file.read(), filename=str(source_path))

    asset_names: set[str] = set()
    tinyfan_namespaces: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == "tinyfan" or imported.name == "tinyfan.flow":
                    tinyfan_namespaces.add(imported.asname or "tinyfan")
        elif isinstance(node, ast.ImportFrom) and node.module in {"tinyfan", "tinyfan.flow"}:
            for imported in node.names:
                if imported.name == "asset":
                    asset_names.add(imported.asname or imported.name)
                elif imported.name == "*":
                    asset_names.add("asset")

    def is_asset_decorator(decorator: ast.expr) -> bool:
        while isinstance(decorator, ast.Call):
            decorator = decorator.func
        if isinstance(decorator, ast.Name):
            return decorator.id in asset_names

        names: list[str] = []
        while isinstance(decorator, ast.Attribute):
            names.append(decorator.attr)
            decorator = decorator.value
        if isinstance(decorator, ast.Name):
            names.append(decorator.id)
        names.reverse()
        return len(names) >= 2 and names[0] in tinyfan_namespaces and names[-1] == "asset"

    class AssetVisitor(ast.NodeVisitor):
        found = False

        def _visit_definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if any(is_asset_decorator(decorator) for decorator in node.decorator_list):
                self.found = True

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._visit_definition(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._visit_definition(node)

        def visit_ClassDef(self, node: ast.ClassDef):
            self._visit_definition(node)
            if not self.found:
                self.generic_visit(node)

    visitor = AssetVisitor()
    visitor.visit(tree)
    return visitor.found


def _package_source_modules(package) -> list[tuple[str, Path]]:
    modules: list[tuple[str, Path]] = []
    for package_path in package.__path__:
        root = Path(package_path)
        for source_path in root.rglob("*.py"):
            relative_path = source_path.relative_to(root)
            if source_path.name == "__init__.py":
                module_parts = relative_path.parts[:-1]
            else:
                module_parts = relative_path.with_suffix("").parts
            if not module_parts:
                # Importing the root package has already executed its __init__.py.
                continue
            modules.append((".".join((package.__name__, *module_parts)), source_path))
    return modules


def import_asset_modules(location: str):
    """Import asset-bearing modules from a module name, package directory, or file."""
    path = Path(location)
    if path.is_dir():
        path = path.resolve()
        module_parts = [path.name]
        parent = path.parent
        while (parent / "__init__.py").is_file():
            module_parts.insert(0, parent.name)
            parent = parent.parent
        sys.path.insert(0, str(parent))
        package = importlib.import_module(".".join(module_parts))
    elif path.is_file():
        sys.path.insert(0, str(path.resolve().parent))
        spec = importlib.util.spec_from_file_location("__tinyfan_repo__", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"fail to load module from `{location}.`")
        package = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = package
        spec.loader.exec_module(package)
    else:
        package = importlib.import_module(location)
    if package.__name__ == "__tinyfan_repo__" or not hasattr(package, "__path__"):
        return
    for module_name, source_path in _package_source_modules(package):
        if _defines_tinyfan_asset(source_path):
            importlib.import_module(module_name)


def assetname2template(name: str):
    return name.replace("_", "-")


class AssetNode:
    asset: Asset
    depends: str
    refs: list[Config | ConfigValue | str | None]
    children: list[Self]
    parents: list[Self]

    def __init__(self, asset):
        self.asset = asset
        self.depends = asset.depends or ""
        self.children = []
        self.parents = []

    def __hash__(self):
        return hash(self.asset.name)

    def asset_module_name(self):
        mod = inspect.getmodule(self.asset.func)
        return mod.__name__ if mod else None

    def rundatatmpl(self, schedule: str, timezone: str):
        return json.dumps(
            {
                "schedule": schedule,
                "timezone": timezone,
                # A backfill's parent workflow has neither timestamp; defer to the child.
                "scheduled_time_b64": (
                    "{{= let ts = 'parameters' in workflow && 'cronScheduleTime' in workflow.parameters"
                    " ? workflow.parameters.cronScheduleTime : workflow.scheduledTime;"
                    " ts == nil ? nil : sprig.b64enc(ts) }}"
                ),
                "parents": {
                    p.asset.name: f"{{{{tasks.{p.asset.name.replace('_', '-')}.outputs.parameters.rundata}}}}"
                    for p in self.parents
                },
                "asset_name": self.asset.name,
                "flow_name": self.asset.flow.name,
                "module_name": self.asset_module_name(),
            }
        )

    def relatives(self, result: set[Self] | None = None) -> set[Self]:
        if result is None:
            result = {self}
        for node in self.parents + self.children:
            if node not in result:
                result.add(node)
                node.relatives(result)
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
            if unknown_names:
                raise ValueError(
                    f"unknown asset args: {', '.join('`' + n + '`' for n in unknown_names)} from asset `{node.asset.name}`"
                )

            params_ids = {name for name in func_param_names if name in self.flow.assets}
            if node.depends:
                assert re.match(VALID_DEPENDS_REGEXP, node.depends)
                depends_ids = set(re.findall(EXTRACT_DEPENDS_REGEXP, node.depends))
                node.parents = [self.nodes[n] for n in sorted(depends_ids.union(params_ids))]
                new_ids = params_ids - depends_ids
                if new_ids:
                    if len(depends_ids) > 1:
                        node.depends = f"({node.depends}) && {' && '.join(sorted(new_ids))}"
                    else:
                        node.depends = f"{node.depends} && {' && '.join(sorted(new_ids))}"
                    assert re.match(VALID_DEPENDS_REGEXP, node.depends)
                for p in node.parents:
                    p.children.append(node)
            else:
                node.parents = [self.nodes[n] for n in sorted(params_ids)]
                for p in node.parents:
                    p.children.append(node)
                node.depends = " && ".join(sorted(params_ids))

            flow_resources = self.flow.resources or {}
            flow_refs = self.flow.configs or {}
            param_resources = [flow_resources[n] for n in func_param_names if n in flow_resources]
            param_resources += [node.asset.store, *(p.asset.store for p in node.parents)]
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

        g: nx.DiGraph = nx.DiGraph()
        g.add_node(self.flow.name, bullet="■")
        for (tz, schedule), relatives in self.relatives_by_schedules().items():
            schedule_node_name = schedule + f" ({tz})"
            g.add_node(schedule_node_name, bullet="○")
            g.add_edge(self.flow.name, schedule_node_name)
            g.add_edges_from([(schedule_node_name, r.asset.name) for r in relatives])
            g.add_edges_from([(d.asset.name, r.asset.name) for r in relatives for d in r.parents])
        return dagviz(g, round_angle=True)

    def compile(
        self,
        embedded: bool = True,
        container: ScriptTemplate | None = None,
        serviceAccountName: str | None = None,
    ) -> str:
        if container is None:
            container = {}
        if len(self.nodes) == 0:
            return ""

        relatives_by_schedules = self.relatives_by_schedules()
        for tz, schedule in relatives_by_schedules:
            if not croniter.croniter.is_valid(schedule):
                raise ValueError(f"invalid schedule: {schedule!r}")
            ZoneInfo(tz)

        source = ""
        if embedded:
            source += embed("six")
            # ponytail: bundle croniter's dateutil imports; install dateutil in the image for broader asset use.
            source += embed(
                "dateutil",
                includes=["__init__.py", "_version.py", "_common.py", "relativedelta.py", "tz/*.py"],
                minify=True,
            )
            source += embed("croniter", includes=["*.py"], minify=True)
            source += embed(
                "tzdata",
                includes=[
                    "**/__init__.py",
                    *(f"zoneinfo/{tz}" for tz in sorted({tz for tz, _ in relatives_by_schedules})),
                ],
            )
            source += embed("tinyfan", excludes=["codegen.py", "utils/embed.py", "**/__pycache__/*"], minify=False)
        source += (
            "from tinyfan.config import CLI_CONFIG_STATE\n"
            f"CLI_CONFIG_STATE.cli_args = {json.dumps(CLI_CONFIG_STATE.cli_args)}\n"
        )
        if embedded:
            root_location = get_root_path(next(iter(self.nodes.values())).asset.func)
            source += embed(root_location)
            if not root_location.endswith(".py"):
                source += """{{=join(map(fromJSON(inputs.parameters.moduledata), {"from " + .module + " import " + .name}), ";")}}\n"""
            source += "asset = {{inputs.parameters.asset_name}}.asset\n"
        else:
            source += (
                """{{=join(map(fromJSON(inputs.parameters.moduledata), {"from " + .module + " import " + .name}), ";")}}\n"""
                "asset = {{inputs.parameters.asset_name}}.asset\n"
            )
        source += (
            "import os\n"
            "from tinyfan.flowrundata import encode_rundata, load_rundata\n"
            f"with open({RUNDATA_INPUT_FILE_PATH!r}, encoding='utf-8') as f:\n"
            "    rundata = load_rundata(f.read())\n"
            "_, rundata = asset.run(rundata)\n"
            f"path = '{RUNDATA_FILE_PATH}'\n"
            "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
            "with open(path, 'w', encoding='ascii') as f:\n"
            "    f.write(encode_rundata(rundata))\n"
        )

        pod_container: dict = {"name": "main"}
        deepmerge(pod_container, copy.deepcopy(container), copy.deepcopy(self.flow.container or {}))
        pod_container["env"] = [env for env in pod_container.get("env", []) if env["name"] != "TINYFAN_SOURCE"] + [
            {"name": "TINYFAN_SOURCE", "value": source}
        ]

        manifests = [
            {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "CronWorkflow",
                "metadata": {
                    "name": f"""{self.flow.name}-{encode_schedule_to_k8sname(tz, schedule)}""",
                    "generateName": f"""{self.flow.name}-{encode_schedule_to_k8sname(tz, schedule)}-""",
                },
                "spec": {
                    "schedules": [schedule],
                    "timezone": tz,
                    "workflowSpec": {
                        "entrypoint": "flow",
                        **dropnone({"serviceAccountName": serviceAccountName or self.flow.serviceAccountName}),
                        "podSpecPatch": yaml_dump({"containers": [pod_container]}),
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
                                **dropnone(
                                    {
                                        "podSpecPatch": node.asset.container
                                        and yaml_dump(
                                            {
                                                "containers": [
                                                    deepmerge(
                                                        {
                                                            "name": "main",
                                                        },
                                                        node.asset.container,
                                                    )
                                                ]
                                            }
                                        ),
                                    }
                                ),
                                "synchronization": {
                                    "mutexes": [{"name": f"{self.flow.name}-{node.asset.name.replace('_', '-')}"}]
                                },
                                "inputs": merge_template_io(
                                    {
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
                                                "name": "moduledata",
                                                "value": "{{= nil }}",
                                            },
                                        ],
                                        "artifacts": [
                                            {
                                                "name": "tinyfan-rundata",
                                                "path": RUNDATA_INPUT_FILE_PATH,
                                                "raw": {"data": "{{inputs.parameters.rundata}}"},
                                            }
                                        ],
                                    },
                                    node.asset.inputs,
                                    INTERNAL_INPUT_PARAMETERS,
                                ),
                                "outputs": merge_template_io(
                                    {
                                        "parameters": [
                                            {
                                                "name": "rundata",
                                                "valueFrom": {
                                                    "path": RUNDATA_FILE_PATH,
                                                },
                                            }
                                        ],
                                    },
                                    node.asset.outputs,
                                    INTERNAL_OUTPUT_PARAMETERS,
                                ),
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
                                            "depends": node.depends.replace("_", "-"),
                                            "template": node.asset.name.replace("_", "-"),
                                            "arguments": {
                                                "parameters": [
                                                    {
                                                        "name": "rundata",
                                                        "value": node.rundatatmpl(schedule, tz),
                                                    },
                                                    {
                                                        "name": "asset_name",
                                                        "value": node.asset.name,
                                                    },
                                                    {
                                                        "name": "moduledata",
                                                        "value": json.dumps(
                                                            [
                                                                {
                                                                    "module": node.asset_module_name(),
                                                                    "name": node.asset.name,
                                                                },
                                                                *(
                                                                    {
                                                                        "module": p.asset_module_name(),
                                                                        "name": p.asset.name,
                                                                    }
                                                                    for p in node.parents
                                                                ),
                                                            ]
                                                        ),
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
    container: ScriptTemplate | None = None,
    serviceAccountName: str | None = None,
) -> str:
    """Generate argocd workflow resource as yaml from tinyfan definitions"""
    if container is None:
        container = {}
    try:
        CLI_CONFIG_STATE.codegen = True
        if flow:
            result = AssetTree(flow).compile(embedded, container, serviceAccountName)
        elif location:
            import_asset_modules(location)
            result = "\n---\n".join(
                AssetTree(flow).compile(embedded, container, serviceAccountName) for flow in FLOW_REGISTER.values()
            )
        else:
            result = "\n---\n".join(
                AssetTree(flow).compile(embedded, container, serviceAccountName) for flow in FLOW_REGISTER.values()
            )
    finally:
        CLI_CONFIG_STATE.codegen = False
    return result
