#!/usr/bin/env python3
import os
import time
import threading
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi import Body
from pydantic import BaseModel
import json  

import requests
import threading

# Global lock to ensure safe writes to the votes file
lock = threading.Lock()

# Global dictionary to store votes
votes = {}

# Import pyraft components
from pyraft.raft import RaftNode
from pyraft.common import Future

# --- Configure logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fastapi_cluster")

# ----------------- KUBERNETES CONFIGURATION CHANGES -----------------
# Read node ID from environment variable
NODE_ID = os.getenv("NODE_ID", "1")

# Kubernetes DNS-based Service Discovery
RAFT_PORT = int(os.getenv("RAFT_PORT", "7010"))
RAFT_SERVICE_NAME = os.getenv("RAFT_SERVICE_NAME", "raft")
RAFT_CLUSTER_SIZE = int(os.getenv("RAFT_CLUSTER_SIZE", "6"))

# Construct the ensemble using Kubernetes DNS resolution
ensemble = {f"raft-{i}": f"raft-{i}.raft.default.svc.cluster.local:7010" for i in range(RAFT_CLUSTER_SIZE)}

logger.info(f"Node {NODE_ID} joining Raft cluster: {ensemble}")

# Create a **single** Raft node per Kubernetes pod
raft_node = RaftNode(
    str(NODE_ID),
    ensemble[NODE_ID],
    ensemble,
    #election_timeout=3.0  # Set election timeout to ensure leader election happens faster
)
raft_node.election_timeout = 4

if hasattr(raft_node, 'election_timeout'):
    raft_node.election_timeout = 3  # Set timeout if supported
else:
    logger.warning("RaftNode does not support election timeout. Skipping...")

# ----------------- FASTAPI SERVER -----------------
app = FastAPI(title="Raft Cluster API", version="1.0")


# Ensure the directory exists before writing to files
DATA_DIR = "/app/data"

def ensure_data_directory():
    """Ensure that the data directory exists before using it."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

# Call this function at the start of the script
ensure_data_directory()

def ensure_file_exists(file_path, default_content="{}"):
    """Ensure the specified file exists, creating it if necessary."""
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write(default_content) 

# ----------------- Voting -----------------
VOTERS_FILE = os.path.join(DATA_DIR, "voters.txt")
RESULTS_FILE = os.path.join(DATA_DIR, "results.txt")
VOTES_FILE = os.path.join(DATA_DIR, "votes.json")


def log_vote(user, candidate):
    """Log individual vote details into voters.txt, ensuring the file exists first."""
    ensure_file_exists(VOTERS_FILE, "")  # Ensure file exists before writing
    with open(VOTERS_FILE, "a") as f:
        f.write(f"{user} voted for {candidate}\n")


def save_results(vote_counts):
    """Save vote counts to results file."""
    with open(RESULTS_FILE, "w") as f:
        json.dump(vote_counts, f, indent=4)

def load_results():
    """Load vote counts from the results file."""
    ensure_file_exists(RESULTS_FILE, "{}")  # Ensure file exists before reading
    with open(RESULTS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def load_votes():
    """Load votes from JSON file, ensuring persistence across restarts."""
    ensure_file_exists(VOTES_FILE, "{}")  # Ensure file exists before reading
    with open(VOTES_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

# Load votes at startup
votes = load_results()

def save_votes(votes):
    """Save votes to JSON file."""
    with open(VOTES_FILE, "w") as f:
        json.dump(votes, f, indent=4)


class VoteRequest(BaseModel):
    user: str
    candidate: str

@app.post("/vote")
def vote(request: dict = Body(...)):
    """Handles voting. The leader node records the vote."""
    global votes

    # Check if this node is the leader
    if raft_node.state != 'l':
        leader_response = get_leader()
        leader = leader_response.get("leader")
        
        if leader is None:
            raise HTTPException(status_code=503, detail="Leader unavailable, try again later.")

        leader_url = f"http://{ensemble[leader].split(':')[0]}:8000/vote"

        # Forward request to leader
        try:
            response = requests.post(leader_url, json=request, timeout=2)
            return response.json()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=503, detail=f"Failed to forward vote to leader: {str(e)}")

    # If leader, process the vote
    candidate = request["candidate"]
    votes = load_results()
    votes[candidate] = votes.get(candidate, 0) + 1

    # Save updated results
    with lock:
        log_vote(request["user"], candidate)  # Save voter details
        save_results(votes)  # Save vote count

    return {"message": f"Vote cast for {candidate}", "votes": votes}

class AppendRequest(BaseModel):
    command: list  # Example: ["set", "key", "value"]

@app.get("/results")
def get_results():
    """Returns the current voting results."""
    try:
        return {"votes": load_results()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching results: {str(e)}")


@app.get("/node/status")
def node_status():
    """Returns the status of the current Raft node"""
    return {
        "node_id": raft_node.nid,
        "state": raft_node.state,
        "term": raft_node.term,
        "is_leader": (raft_node.state == 'l')
    }


@app.get("/status")
def get_status():
    """Alias for node status"""
    return node_status()


@app.get("/node/log")
def node_log():
    """Retrieves the log entries of the node and reconstructs votes from logs."""
    global votes

    try:
        start_index = raft_node.log.start_index()
        log_entries = raft_node.log.get_range(start_index)

        # Rebuild votes from Raft logs
        reconstructed_votes = {}
        for item in log_entries:
            cmd = item.cmd
            if cmd[0] == "vote":
                user, candidate = cmd[1], cmd[2]
                reconstructed_votes[candidate] = reconstructed_votes.get(candidate, 0) + 1

        # Replace current votes with reconstructed votes
        votes = reconstructed_votes

        return {"log": log_entries, "votes": votes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/node/append")
def append_entry(req: AppendRequest):
    """Appends a new entry to the log if this node is the leader"""
    if raft_node.state != 'l':
        # Force election if no leader is found
        if not any(node for node in ensemble if raft_node.state == 'l'):
            logger.warning("No leader detected! Forcing election...")
            # Force an election by resetting election timeout
            raft_node.election_timeout = 4  # Force quick re-election


        raise HTTPException(status_code=400, detail="Not the leader; cannot append entry.")
    
    try:
        future = Future(req.command, worker_offset=0)
        raft_node.append_entry(future)
        return {"message": f"Appended command: {req.command}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/leader")
def get_leader():
    """Returns the current leader node."""
    for node_id, node_url in ensemble.items():
        try:
            # Extract base URL (without port) and check leader status
            response = requests.get(f"http://{node_url.split(':')[0]}:8000/status", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get("is_leader"):
                    return {"leader": node_id}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to connect to {node_id} ({node_url}): {e}")
            continue  # Skip unreachable nodes
    return {"leader": None}


# ----------------- THREAD MANAGEMENT -----------------
def start_raft_node():
    """Starts the Raft node in a separate thread"""
    logger.info(f"Starting Raft Node {NODE_ID} at {ensemble[NODE_ID]}")
    threading.Thread(target=raft_node.start, daemon=True).start()
    time.sleep(5)  # Allow time for stabilization

def monitor_leader():
    """Continuously monitor leadership and trigger election if leader is missing."""
    last_leader = None

    while True:
        time.sleep(1)  # Check more frequently (every 0.5s for faster detection)

        # Get the current leader from API
        leader_response = get_leader()
        leader = leader_response.get("leader")

        if leader is None:
            logger.warning("Leader is missing! Adjusting timeout to force election...")
            try:
                raft_node.election_timeout = 4  # Reduce timeout to trigger election
            except Exception as e:
                logger.error(f"Election trigger failed: {e}")
        elif leader != last_leader:
            last_leader = leader
            logger.info("Restoring votes from disk after leader change...")
            global votes
            votes = load_results()

if __name__ == "__main__":
    start_raft_node()
    threading.Thread(target=monitor_leader, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
