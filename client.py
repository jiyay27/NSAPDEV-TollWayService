import socket
import threading
import time
import random

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12345
ENTRY_EXIT_POINTS = 18
TOLL_BOOTH_LIMITS = {"plaza": 6, "regular": 4}

vehicle_plates = [f"CAR{str(i).zfill(3)}" for i in range(1, 51)]
simulated_on_highway = set()

def send_request(command, plate, point, booth_id):
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((SERVER_HOST, SERVER_PORT))
        message = f"{command},{plate},{point},{booth_id}"
        client.send(message.encode())
        response = client.recv(1024).decode()
        client.close()
        return response
    except Exception as e:
        return f"Error connecting to server: {e}"

def simulate_transaction():
    if simulated_on_highway and random.random() < 0.5:
        plate = random.choice(list(simulated_on_highway))
        exit_point = random.randint(0, ENTRY_EXIT_POINTS - 1)
        booth_limit = TOLL_BOOTH_LIMITS["plaza"] if exit_point in [0, ENTRY_EXIT_POINTS - 1] else TOLL_BOOTH_LIMITS["regular"]
        booth_id = random.randint(1, booth_limit)
        response = send_request("EXIT", plate, exit_point, booth_id)
        if "exited" in response:
            simulated_on_highway.remove(plate)
        print(f"[EXIT] Plate: {plate}, Exit Point: {exit_point}, Booth: {booth_id} -> {response}")
    else:
        plate = random.choice(vehicle_plates)
        if plate in simulated_on_highway:
            return
        entry_point = random.randint(0, ENTRY_EXIT_POINTS - 1)
        booth_limit = TOLL_BOOTH_LIMITS["plaza"] if entry_point in [0, ENTRY_EXIT_POINTS - 1] else TOLL_BOOTH_LIMITS["regular"]
        booth_id = random.randint(1, booth_limit)
        response = send_request("ENTRY", plate, entry_point, booth_id)
        if "entered" in response:
            simulated_on_highway.add(plate)
        print(f"[ENTRY] Plate: {plate}, Entry Point: {entry_point}, Booth: {booth_id} -> {response}")

def simulated_toll_booth_client(client_id):
    while True:
        simulate_transaction()
        time.sleep(random.uniform(1, 5))

def start_automated_simulation(num_clients=5):
    threads = []
    for i in range(num_clients):
        thread = threading.Thread(target=simulated_toll_booth_client, args=(i+1,), daemon=True)
        threads.append(thread)
        thread.start()
        print(f"Simulated toll booth client {i+1} started.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Simulation terminated.")

if __name__ == "__main__":
    start_automated_simulation(num_clients=5)