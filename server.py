import socket
import threading
import dotenv

# Server configurations
HOST = "0.0.0.0"
PORT = 31194

# Toll configuration
TOLL_RATE_PER_KM = 2
ENTRY_EXIT_POINTS = 18
TOLL_BOOTH_LIMITS = {  
    "regular": 4,
    "plaza": 6
}

# Highway tracking
vehicles_on_highway = {}  
total_vehicles = 0
total_fees_collected = 0
lock = threading.Lock()

def handle_client(conn, addr):
    global total_vehicles, total_fees_collected

    print(f"[NEW CONNECTION] {addr} connected.")
    with conn:
        while True:
            try:
                data = conn.recv(1024).decode()
                if not data:
                    break

                command, plate, point, booth_id = data.split(',')
                point = int(point)

                # Validate entry/exit point
                if point < 0 or point >= ENTRY_EXIT_POINTS:
                    response = f"Invalid entry/exit point! Must be between 0 and {ENTRY_EXIT_POINTS - 1}."

                else:
                    with lock:
                        if command == "ENTRY":
                            if plate in vehicles_on_highway:
                                response = f"ERROR: Vehicle {plate} is already on the highway!"
                            else:
                                vehicles_on_highway[plate] = point
                                response = f"Vehicle {plate} entered at point {point} through Booth {booth_id}."
                                total_vehicles += 1

                        elif command == "EXIT":
                            if plate not in vehicles_on_highway:
                                response = f"ERROR: Vehicle {plate} is not on the highway!"
                            else:
                                entry_point = vehicles_on_highway.pop(plate)
                                distance = abs(point - entry_point)
                                toll_fee = distance * TOLL_RATE_PER_KM
                                total_fees_collected += toll_fee
                                response = f"Vehicle {plate} exited at point {point} via Booth {booth_id}. Toll Fee: ${toll_fee:.2f}"

                        elif command == "STATUS":
                            response = f"Vehicles on highway: {len(vehicles_on_highway)}, Total vehicles: {total_vehicles}, Total toll collected: ${total_fees_collected:.2f}"

                        else:
                            response = "ERROR: Invalid command!"

                conn.send(response.encode())

            except Exception as e:
                print(f"Error handling client {addr}: {e}")
                break

    print(f"[DISCONNECTED] {addr} disconnected.")


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"[LISTENING] Server is listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")


if __name__ == "__main__":
    start_server()
