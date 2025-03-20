### *Step-by-Step Guide to Set Up and Run the Raft Cluster on a New Device*
---

### *🛠 Prerequisites (Ensure These Are Installed)*
Before running the commands, ensure the new device has:
- *Docker*
- *Kubernetes (kubectl)*
- *Minikube*
- *Python 3.9+*
- *pip*

If any of these are missing, install them first.

---
## *🚀 Step 1: unzip*
unzip cloud_project.zip


---

## *🐳 Step 2: Start & Configure Minikube*
bash
minikube start --driver=docker  # Start Minikube cluster
minikube status  # Ensure Minikube is running


---

## *📦 Step 3: Build & Load Docker Image in Minikube*
Since Kubernetes will pull the image from Minikube's internal Docker registry, run:
bash
eval $(minikube docker-env) 
docker build -t my-raft-app .  


Verify the image exists in Minikube:
bash
docker images | grep my-raft-app


---

## *📝 Step 4: Apply Kubernetes YAML Configurations*
Navigate to the yamls/ directory:
bash
cd yamls


Deploy the *Raft StatefulSet and Services*:
bash
kubectl apply -f raft-statefulset.yaml
kubectl apply -f raft-rest-service.yaml
kubectl apply -f raft-fastapi-service.yaml


Verify all components are running:
bash
kubectl get pods -o wide  # Check if all pods are Running
kubectl get services  # Ensure services are correctly deployed


---

## *🌍 Step 5: Port Forward to Access the API*
bash
kubectl port-forward svc/raft-fastapi 8000:8000


Now, you can check the cluster's status:
bash
curl http://localhost:8000/status


---

## *📡 Step 6: Check Cluster Node Status*
Run this to verify which nodes are available and which one is the *leader*:
bash
kubectl exec -it raft-0 -- curl http://localhost:8000/status
kubectl exec -it raft-1 -- curl http://localhost:8000/status
kubectl exec -it raft-2 -- curl http://localhost:8000/status
kubectl exec -it raft-3 -- curl http://localhost:8000/status
kubectl exec -it raft-4 -- curl http://localhost:8000/status
kubectl exec -it raft-5 -- curl http://localhost:8000/status


You should see one of them having "is_leader": true.

---

## *🛠️ Step 7: Test Leadership Election*
To *delete the leader and trigger re-election, first **identify the leader*, then delete it:
bash
kubectl delete pod <leader-pod-name>

Check if a new leader is elected:
bash
kubectl get pods
kubectl exec -it raft-0 -- curl http://localhost:8000/status


---

## *🛑 Step 8: Shut Down Everything (Optional)*
If needed, tear down Minikube and Kubernetes resources:
bash
kubectl delete -f raft-statefulset.yaml
kubectl delete -f raft-rest-service.yaml
kubectl delete -f raft-fastapi-service.yaml
minikube stop
minikube delete
