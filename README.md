### **Step-by-Step Guide to Set Up and Run the Raft Cluster on a New Device**
---

### **Prerequisites (Ensure These Are Installed)**
Before running the commands, ensure the new device has:
- **Python 3.9+**
- **[Docker](https://docs.docker.com/engine/install/ubuntu/)**
- **[Kubernetes](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)**
- **[Minikube](https://minikube.sigs.k8s.io/docs/start/?arch=%2Flinux%2Fx86-64%2Fstable%2Fbinary+download)**

Webiste for package installation are linked

---

## **Start & Configure Minikube**
```bash
sudo usermod -aG docker $USER && newgrp docker
minikube start --driver=docker  # Start Minikube cluster
minikube status  # Ensure Minikube is running
```

---

## **Build & Load Docker Image in Minikube**
Since Kubernetes will pull the image from Minikube's internal Docker registry, run:

```bash
eval $(minikube docker-env) # Point Docker to Minikube 
docker build -t my-raft-app .  
```

Verify the image exists in Minikube:
```bash
docker images | grep my-raft-app
```

---

## **Apply Kubernetes YAML Configurations**

Deploy the **Raft StatefulSet and Services**:
```bash
kubectl apply -f raft-statefulset.yaml
kubectl apply -f raft-rest-service.yaml
kubectl apply -f raft-fastapi-service.yaml
```

Verify all components are running:
```bash
kubectl get pods -o wide  # Check if all pods are Running
kubectl get services  # Ensure services are correctly deployed
```

---

##  **Port Forward to Access the API**
Run this in another terminal
```bash
kubectl port-forward svc/raft-fastapi 8000:8000
```

---

##  **Check Cluster Node Status**
Run this to verify which nodes are available and which one is the **leader**:
```bash
kubectl exec -it raft-0 -- curl http://localhost:8000/status
kubectl exec -it raft-1 -- curl http://localhost:8000/status
kubectl exec -it raft-2 -- curl http://localhost:8000/status
kubectl exec -it raft-3 -- curl http://localhost:8000/status
kubectl exec -it raft-4 -- curl http://localhost:8000/status
kubectl exec -it raft-5 -- curl http://localhost:8000/status
```

You should see one of them having `"is_leader": true.`

---

##  **Test Leadership Election**
To delete the leader and trigger re-election, first **identify** the leader, then delete it:
```bash
kubectl delete pod <leader-pod-name>
```

Check if a new leader is elected:
```bash
kubectl exec -it <pod-name-any> -- curl http://localhost:8000/leader
```

---

## **Voting System**

```bash
kubectl exec -it <leader-pod-name> -- curl -X POST "http://localhost:8000/vote" -H "Content-Type: application/json" -d '{"user": "Alice", "candidate": "Bob"}'


kubectl exec -it <pod-name> -- curl http://localhost:8000/results
```

---

##  **Step 9: Shut Down Everything *(Optional)***
If needed, tear down Minikube and Kubernetes resources:

```bash
kubectl delete -f raft-statefulset.yaml
kubectl delete -f raft-rest-service.yaml
kubectl delete -f raft-fastapi-service.yaml
minikube stop
minikube delete
```