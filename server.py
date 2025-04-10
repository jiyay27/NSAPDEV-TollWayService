import socket
import threading
import json
import os
import random
import time
from datetime import datetime

HOST = '0.0.0.0'
PORT = 8081

TOTAL_POINTS = 18 
PLAZA_POINTS = [0, 17]  
REGULAR_TOLL_RATE = 2.0
TRAVEL_DELAY_PER_POINT = 3

current_vehicles = {} 
completed_vehicles = set()  # so no same vehicles re-enter
total_vehicles = 0 
total_fees_collected = 0.0 

connected_booths = {} # maps booth_id to connection
booth_vehicles = {}  # Track which booth each vehicle entered from

data_lock = threading.Lock()  # sync thread access to data

LOG_FILE = "toll_log.txt"
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

def log_transaction(log_data):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_data) + "\n")

def calculate_toll_fee(entry_point, exit_point):
    distance = abs(exit_point - entry_point)
    return distance * REGULAR_TOLL_RATE

def simulate_travel_time(entry_point, exit_point):
    distance = abs(exit_point - entry_point)
    delay = distance * TRAVEL_DELAY_PER_POINT
    
    # add more delay randomness
    delay *= random.uniform(3, 20)
    
    return delay

def handle_entry_request(booth_id, point, vehicle_id, booth_key):
    global total_vehicles
    
    # check if the vehicle is already on the highway
    with data_lock:
        if vehicle_id in current_vehicles:
            return {
                "status": "Failure",
                "message": f"Vehicle {vehicle_id} is already on the highway"
            }
        if vehicle_id in completed_vehicles:
            return {
                "status": "Failure",
                "message": f"Vehicle {vehicle_id} has already completed a journey"
            }
    
    # Log vehicle entry onto text file
    with data_lock:
        current_vehicles[vehicle_id] = {
            "entry_point": point,
            "entry_booth": booth_id,
            "entry_time": datetime.now().timestamp()
        }
        total_vehicles += 1
        
        # Track which booth this vehicle entered from
        if booth_key not in booth_vehicles:
            booth_vehicles[booth_key] = set()
        booth_vehicles[booth_key].add(vehicle_id)
    
    # transaction details
    log_data = {
        "action": "Entry",
        "vehicle_id": vehicle_id,
        "entry_point": point,
        "booth_id": booth_id,
        "timestamp": datetime.now().isoformat()
    }
    log_transaction(log_data)
    
    # print successful entry
    print(f"[ENTRY] Vehicle {vehicle_id} entered at Point {point+1} Booth {booth_id}")
    
    return {
        "status": "Success",
        "vehicle_id": vehicle_id,
        "message": f"Vehicle {vehicle_id} entered at point {point}"
    }

def handle_exit_request(booth_id, point):
    global total_fees_collected
    
    candidate_vehicles = []
    
    current_time = datetime.now().timestamp()
    
    # let vehicles exit that entered from a lower point number
    with data_lock:
        for vehicle_id, data in list(current_vehicles.items()):
            entry_point = data["entry_point"]
            entry_booth = data["entry_booth"]
            entry_time = data["entry_time"]
            
            # Only allow exit if entry_point is less than current point
            if entry_point >= point:
                continue
                
            # Calculate expected travel time
            expected_travel_time = simulate_travel_time(entry_point, point)
            actual_travel_time = current_time - entry_time
            
            # only allow exit if enough time has passed for realistic travel
            if actual_travel_time >= expected_travel_time:
                candidate_vehicles.append((vehicle_id, entry_point, actual_travel_time))
    
    if not candidate_vehicles:
        return {
            "status": "Failure",
            "message": "No vehicles available for exit"
        }
    
    # choose a random vehicle to exit from candidates
    vehicle_id, entry_point, travel_time = random.choice(candidate_vehicles)
    
    # calculate toll
    toll_fee = calculate_toll_fee(entry_point, point)
    
    # move from current to completed
    with data_lock:
        # Remove vehicle from the booth that entered it
        for booth_key, vehicles in booth_vehicles.items():
            if vehicle_id in vehicles:
                vehicles.remove(vehicle_id)
        
        del current_vehicles[vehicle_id]
        completed_vehicles.add(vehicle_id)
        total_fees_collected += toll_fee
    
    log_data = {
        "action": "Exit",
        "vehicle_id": vehicle_id,
        "entry_point": entry_point,
        "exit_point": point,
        "booth_id": booth_id,
        "toll_fee": toll_fee,
        "travel_time": travel_time,
        "timestamp": datetime.now().isoformat()
    }
    log_transaction(log_data)
    
    print(f"[EXIT] Vehicle {vehicle_id} exited at Point {point+1} Booth {booth_id}, "
          f"Toll fee: ${toll_fee:.2f}")#, Travel time: {travel_time:.2f}s")
    
    return {
        "status": "Success",
        "vehicle_id": vehicle_id,
        "entry_point": entry_point,
        "toll_fee": toll_fee,
        "travel_time": travel_time,
        "message": f"Vehicle {vehicle_id} exited at point {point}. Toll fee: ${toll_fee:.2f}"
    }

def process_remaining_vehicles_from_booth(booth_key):
    # Get vehicles that entered from this booth
    vehicles_to_process = []
    with data_lock:
        if booth_key in booth_vehicles:
            vehicles_to_process = list(booth_vehicles[booth_key])
    
    if not vehicles_to_process:
        return
    
    for vehicle_id in vehicles_to_process:
        # check if vehicle is still on highway
        with data_lock:
            if vehicle_id not in current_vehicles:
                continue
            
            vehicle_data = current_vehicles[vehicle_id]
            entry_point = vehicle_data["entry_point"]
            entry_time = vehicle_data["entry_time"]
        
        valid_exit_points = [p for p in range(TOTAL_POINTS) if p > entry_point]
        if not valid_exit_points:
            # If no valid exit points, use last point
            exit_point = TOTAL_POINTS - 1
        else:
            exit_point = random.choice(valid_exit_points)
        
        # calculate toll and travel time
        toll_fee = calculate_toll_fee(entry_point, exit_point)
        current_time = datetime.now().timestamp()
        travel_time = current_time - entry_time
        
        # process exit
        with data_lock:
            # remove vehicle from booth tracking
            if booth_key in booth_vehicles and vehicle_id in booth_vehicles[booth_key]:
                booth_vehicles[booth_key].remove(vehicle_id)
            
            if vehicle_id in current_vehicles:
                del current_vehicles[vehicle_id]
                
            completed_vehicles.add(vehicle_id)
            total_fees_collected += toll_fee
        
        # log the forced exit
        log_data = {
            "action": "Forced Exit",
            "vehicle_id": vehicle_id,
            "entry_point": entry_point,
            "exit_point": exit_point,
            "booth_id": "SYSTEM",
            "toll_fee": toll_fee,
            "travel_time": travel_time,
            "timestamp": datetime.now().isoformat(),
            "note": "Forced exit due to booth disconnection"
        }
        log_transaction(log_data)
        
        print(f"[FORCED EXIT] Vehicle {vehicle_id} forcibly exited at Point {exit_point+1}, "
              f"Toll fee: ${toll_fee:.2f}")#, Travel time: {travel_time:.2f}s")

def handle_booth_connection(conn, addr, booth_id, point, is_entry):
    if is_entry:
        booth_type = "Entry"
    else:
        booth_type = "Exit"

    point_name = f"Point {point+1}"
    
    # generate unique key for booth to register on connection
    booth_key = f"{point}-{booth_id}-{'entry' if is_entry else 'exit'}"
    
    print(f"[CONNECTED] {booth_type} Booth {booth_id} at {point_name} connected from {addr}")
    
    try:
        # register this connection
        with data_lock:
            connected_booths[booth_key] = conn
        
        while True:
            # wait for a request from the booth
            try:
                data = conn.recv(1024).decode()
                if not data:
                    break  # connection closed
                
                request = json.loads(data)
                action = request.get("action")
                
                # process based on action type
                if action == "entry" and is_entry:
                    # Get vehicle ID from client request
                    vehicle_id = request.get("vehicle_id")
                    if not vehicle_id:
                        response = {
                            "status": "Failure",
                            "message": "No vehicle ID provided for entry"
                        }
                    else:
                        response = handle_entry_request(booth_id, point, vehicle_id, booth_key)

                elif action == "exit" and not is_entry:
                    response = handle_exit_request(booth_id, point)

                else:
                    response = {
                        "status": "Failure",
                        "message": f"Invalid action {action} for {booth_type} booth"
                    }
                
                # send response back to the booth
                conn.send(json.dumps(response).encode())
                
            except json.JSONDecodeError:
                print(f"[ERROR] Invalid JSON from {booth_type} Booth {booth_id}")
                continue
            except Exception as e:
                print(f"[ERROR] Error handling {booth_type} Booth {booth_id}: {e}")
                break

    finally:
        # Process any remaining vehicles from this booth before disconnecting
        if is_entry:  # Only need to do this for entry booths
            process_remaining_vehicles_from_booth(booth_key)
            
        # close connection
        with data_lock:
            if booth_key in connected_booths:
                del connected_booths[booth_key]
                
            # Clean up booth_vehicles entry if empty
            if booth_key in booth_vehicles and not booth_vehicles[booth_key]:
                del booth_vehicles[booth_key]
                
        print(f"[DISCONNECTED] {booth_type} Booth {booth_id} at {point_name} disconnected")

def stats_printer():
    while True:
        with data_lock:
            vehicles_count = len(current_vehicles)
            total_count = total_vehicles
            fees = total_fees_collected
            completed = len(completed_vehicles)
            booth_count = len(connected_booths)
        
        print(f"\n[STATS] Current: {vehicles_count} vehicles, "
              f"Total: {total_count} vehicles, "
              f"Completed: {completed} vehicles, "
              f"Connected Booths: {booth_count}, "
              f"Fees Collected: ${fees:.2f}\n")
        
        time.sleep(3)

def start_server():
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server.bind((HOST, PORT))
        server.listen(100)  # Increased backlog for multiple concurrent connections
        print(f"[LISTENING] Server is listening on {HOST}:{PORT}")

        stats_thread = threading.Thread(target=stats_printer, daemon=True)
        stats_thread.start()

        print("[SERVER] Highway toll system ready. Waiting for booth connections...")
        
        while True:
            conn, addr = server.accept()
            
            try:
                data = conn.recv(1024).decode()
                if not data:
                    conn.close()
                    continue
                
                # parse booth registration
                register_info = json.loads(data)
                booth_id = register_info.get("booth_id")
                point = register_info.get("point")
                is_entry = register_info.get("is_entry", True)
                
                if not isinstance(booth_id, int) or not isinstance(point, int):
                    print(f"[ERROR] Invalid booth registration from {addr}: {register_info}")
                    conn.send(json.dumps({"status": "Failure", "message": "Invalid registration"}).encode())
                    conn.close()
                    continue
                
                # Accept the registration
                conn.send(json.dumps({"status": "Success", "message": "Booth registered"}).encode())
                
                # Start a thread to handle this booth
                client_thread = threading.Thread(
                    target=handle_booth_connection, 
                    args=(conn, addr, booth_id, point, is_entry),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                print(f"[ERROR] Error registering booth from {addr}: {e}")
                conn.close()
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server shutting down...")
        
        # Process any remaining vehicles on exit
        print("[SHUTDOWN] Processing remaining vehicles...")
        remaining_count = 0
        with data_lock:
            remaining_count = len(current_vehicles)
        
        if remaining_count > 0:
            # Collect all booth keys
            booth_keys = list(booth_vehicles.keys())
            for booth_key in booth_keys:
                process_remaining_vehicles_from_booth(booth_key)
                
        print(f"[SHUTDOWN] Processed {remaining_count} remaining vehicles")
        
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
    finally:
        if 'server' in locals():
            server.close()

if __name__ == "__main__":
    start_server()