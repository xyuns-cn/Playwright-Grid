#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time : 2024/5/20 14:40
# @Author : xinnn
# @File : hub.py
# @Describe:
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import uvicorn
import socket
import threading
import time
import json
import asyncio
import signal
import random

app = FastAPI()


class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
        self.pending_responses = {}

    async def connect(self, websocket: WebSocket, node_id: str):
        await websocket.accept()
        self.active_connections[node_id] = websocket
        print(f"Node {node_id} connected")

    def disconnect(self, node_id: str):
        self.active_connections.pop(node_id, None)
        self.pending_responses.pop(node_id, None)
        print(f"Node {node_id} disconnected")

    async def receive_data(self, node_id: str, message: str):
        data = json.loads(message)
        if data.get("type") == "heartbeat":
            print(f"Heartbeat from node {node_id}: {data['data']}")
        elif data.get("type") == "response":
            future = self.pending_responses.pop(node_id, None)
            if future:
                future.set_result(data['data'])
            print(f"Response from node {node_id}: {data['data']}")
        else:
            print(f"Unknown message from node {node_id}: {message}")

    async def send_request(self, request_data: dict):
        if not self.active_connections:
            raise HTTPException(status_code=404, detail="No connected nodes available")

        node_id = random.choice(list(self.active_connections.keys()))
        websocket = self.active_connections[node_id]
        future = asyncio.get_event_loop().create_future()
        self.pending_responses[node_id] = future
        await websocket.send_text(json.dumps(request_data))
        return await future


manager = ConnectionManager()


@app.websocket("/ws/{node_id}")
async def websocket_endpoint(websocket: WebSocket, node_id: str):
    await manager.connect(websocket, node_id)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.receive_data(node_id, data)
    except WebSocketDisconnect:
        manager.disconnect(node_id)


@app.post("/send-request/")
async def send_request_to_random_node(request_data: dict):
    response = await manager.send_request({"type": "request", "data": request_data})
    return response


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))  # 使用公共DNS来获取本地IP
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def broadcast_hub_address():
    BROADCAST_PORT = 37020
    hub_ip = get_local_ip()
    hub_port = 8000
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            s.sendto(f"hub:{hub_ip}:{hub_port}".encode('utf-8'), ('255.255.255.255', BROADCAST_PORT))
            time.sleep(5)


def handle_exit(signum, frame):
    print("Exiting...")
    uvicorn_server.should_exit = True


if __name__ == "__main__":
    broadcast_thread = threading.Thread(target=broadcast_hub_address)
    broadcast_thread.daemon = True
    broadcast_thread.start()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    uvicorn_server = uvicorn.Server(config=uvicorn.Config(app, host="0.0.0.0", port=8000))
    try:
        uvicorn_server.run()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, exiting...")
