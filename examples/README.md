# How to run

```bash
# setup k3d
k3d cluster create tinyfan
kubectl config use-context k3d-tinyfan
# install argowf
kubectl create namespace argo
kubectl apply -n argo -f "https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml"
# apply manifests
tinyfan examples/getting-started.py | kubectl apply -n argo -f -
```
